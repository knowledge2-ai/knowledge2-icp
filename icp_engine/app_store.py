from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .criteria_editor import format_criteria_markdown, lint_criteria_markdown
from .prospects import build_lead_prospects
from .seed_defaults import SEEDED_CRITERIA_MARKDOWN, SEEDED_LISTS, SEEDED_PROMPTS, SEEDED_SETTINGS, SEED_RUN_ID, seeded_run


DEFAULT_STATE_DIR = Path(os.environ.get("ICP_APP_STATE_DIR", "out/app_state"))
DEFAULT_ICP_PATH = Path(os.environ.get("ICP_CRITERIA_PATH", "icp.md"))
LEAD_STATUSES = ("New", "Review", "Qualified", "Rejected", "Exported")
SOURCE_TYPES = ("serp_query", "portfolio_url", "manual_seed", "apollo_query")
QUALITY_DIMENSIONS = ("score", "persona", "outreach")
QUALITY_RATINGS = ("positive", "neutral", "negative")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class AppStore:
    def __init__(self, state_dir: Path | str = DEFAULT_STATE_DIR, icp_path: Path | str = DEFAULT_ICP_PATH) -> None:
        self.state_dir = Path(state_dir)
        self.icp_path = Path(icp_path)
        self.criteria_path = self.state_dir / "criteria.md"
        self.criteria_versions_path = self.state_dir / "criteria_versions.json"
        self.prompts_path = self.state_dir / "prompts.json"
        self.settings_path = self.state_dir / "settings.json"
        self.lists_path = self.state_dir / "lists.json"
        self.lead_states_path = self.state_dir / "lead_states.json"
        self.lead_views_path = self.state_dir / "lead_views.json"
        self.audit_log_path = self.state_dir / "audit_log.json"
        self.sources_path = self.state_dir / "sources.json"
        self.source_scans_path = self.state_dir / "source_scans.json"
        self.provider_usage_path = self.state_dir / "provider_usage.json"
        self.quality_feedback_path = self.state_dir / "quality_feedback.json"
        self.runs_dir = self.state_dir / "runs"
        self.index_path = self.state_dir / "runs.json"

    def ensure(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def load_criteria(self) -> dict[str, Any]:
        self.ensure()
        if self.criteria_path.exists():
            markdown = self.criteria_path.read_text(encoding="utf-8")
            source = str(self.criteria_path)
            updated_at = datetime.fromtimestamp(self.criteria_path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
        elif self.icp_path.exists():
            markdown = self.icp_path.read_text(encoding="utf-8")
            source = str(self.icp_path)
            updated_at = datetime.fromtimestamp(self.icp_path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
        else:
            markdown = SEEDED_CRITERIA_MARKDOWN
            source = "seed:icp.md"
            updated_at = now_iso()
        return {
            "markdown": markdown,
            "source": source,
            "updated_at": updated_at,
            "hash": stable_hash(markdown),
        }

    def save_criteria(self, markdown: str) -> dict[str, Any]:
        self.ensure()
        previous = self.load_criteria()
        cleaned = format_criteria_markdown(markdown)
        history = self._criteria_history_with(previous)
        self.criteria_path.write_text(cleaned, encoding="utf-8")
        saved = self.load_criteria()
        history = _append_unique_criteria_version(history, saved)
        self.criteria_versions_path.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
        return saved

    def lint_criteria(self, markdown: str) -> dict[str, Any]:
        return lint_criteria_markdown(markdown)

    def list_criteria_versions(self) -> list[dict[str, Any]]:
        return self._criteria_history_with(self.load_criteria())

    def restore_criteria_version(self, version_id: str) -> dict[str, Any] | None:
        history = self.list_criteria_versions()
        selected = next((item for item in history if item.get("id") == version_id or item.get("hash") == version_id), None)
        if not selected:
            return None
        self.criteria_path.write_text(str(selected.get("markdown", "")), encoding="utf-8")
        return self.load_criteria()

    def load_prompts(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.prompts_path, list)
        if value is None:
            return [dict(item) for item in SEEDED_PROMPTS]
        return [item for item in value if isinstance(item, dict)]

    def load_settings(self) -> dict[str, Any]:
        self.ensure()
        value = _load_json_file(self.settings_path, dict)
        if value is None:
            return dict(SEEDED_SETTINGS)
        return {**SEEDED_SETTINGS, **value}

    def load_lists(self) -> dict[str, Any]:
        self.ensure()
        value = _load_json_file(self.lists_path, dict)
        if value is None:
            return json.loads(json.dumps(SEEDED_LISTS))
        return {**json.loads(json.dumps(SEEDED_LISTS)), **value}

    def load_sources(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.sources_path, list)
        sources = value if value is not None else _default_sources()
        return [_normalize_source_record(item) for item in sources if isinstance(item, dict) and item.get("name")]

    def save_source(
        self,
        name: str,
        *,
        source_type: str,
        value: str,
        source_group: str = "",
        schedule: str = "",
        enabled: bool = True,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        clean_name = " ".join(name.strip().split())
        clean_value = value.strip()
        clean_type = _normalize_source_type(source_type)
        if not clean_name:
            raise ValueError("Source name is required.")
        if not clean_value:
            raise ValueError("Source value is required.")
        now = now_iso()
        sources = self.load_sources()
        record_id = source_id or stable_hash(f"{clean_type}:{clean_name.lower()}:{clean_value.lower()}")
        previous = next((item for item in sources if item.get("id") == record_id), {})
        record = {
            "id": record_id,
            "name": clean_name,
            "type": clean_type,
            "value": clean_value,
            "source_group": " ".join(source_group.strip().split()) or _source_group_for_type(clean_type),
            "schedule": _normalize_source_schedule(schedule),
            "enabled": bool(enabled),
            "created_at": str(previous.get("created_at") or now),
            "updated_at": now,
            "last_scan_at": str(previous.get("last_scan_at") or ""),
            "last_status": str(previous.get("last_status") or "never_scanned"),
            "last_candidate_count": int(previous.get("last_candidate_count") or 0),
            "last_warning_count": int(previous.get("last_warning_count") or 0),
        }
        next_sources = [item for item in sources if item.get("id") != record_id]
        next_sources.append(record)
        self.sources_path.write_text(json.dumps(sorted(next_sources, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "source.saved",
            subject_type="source",
            subject_id=record_id,
            details={"name": clean_name, "type": clean_type, "source_group": record["source_group"]},
        )
        return record

    def record_source_scan(
        self,
        source_id: str,
        *,
        status: str,
        candidates: list[dict[str, Any]],
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        source = next((item for item in self.load_sources() if item.get("id") == source_id), None)
        if not source:
            raise ValueError("Source not found.")
        now = now_iso()
        clean_candidates = [_candidate_preview_record(item) for item in candidates if isinstance(item, dict)]
        clean_warnings = [str(item) for item in warnings or [] if str(item).strip()]
        scan = {
            "id": stable_hash(f"{now}:{source_id}:{len(clean_candidates)}:{len(clean_warnings)}"),
            "source_id": source_id,
            "source_name": source.get("name", ""),
            "source_type": source.get("type", ""),
            "source_group": source.get("source_group", ""),
            "status": status,
            "scanned_at": now,
            "candidate_count": len(clean_candidates),
            "warning_count": len(clean_warnings),
            "warnings": clean_warnings[:20],
            "candidates": clean_candidates[:100],
        }
        scans = self.list_source_scans(limit=500)
        scans.append(scan)
        self.source_scans_path.write_text(json.dumps(scans[-500:], indent=2, sort_keys=True), encoding="utf-8")

        sources = self.load_sources()
        for item in sources:
            if item.get("id") != source_id:
                continue
            item["last_scan_at"] = now
            item["last_status"] = status
            item["last_candidate_count"] = len(clean_candidates)
            item["last_warning_count"] = len(clean_warnings)
            item["updated_at"] = now
        self.sources_path.write_text(json.dumps(sorted(sources, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "source.scan",
            subject_type="source",
            subject_id=source_id,
            details={"status": status, "candidate_count": len(clean_candidates), "warning_count": len(clean_warnings)},
        )
        return scan

    def list_source_scans(self, *, source_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.source_scans_path, list)
        scans = [item for item in value or [] if isinstance(item, dict)]
        if source_id:
            scans = [item for item in scans if item.get("source_id") == source_id]
        return scans[-max(1, min(limit, 500)) :]

    def source_coverage(self) -> dict[str, Any]:
        sources = self.load_sources()
        scans = self.list_source_scans(limit=500)
        domains = {
            str(candidate.get("domain") or "")
            for scan in scans
            for candidate in scan.get("candidates", [])
            if isinstance(candidate, dict) and candidate.get("domain")
        }
        return {
            "source_count": len(sources),
            "enabled_count": sum(1 for item in sources if item.get("enabled")),
            "source_type_counts": _count_by_key(sources, "type"),
            "source_group_counts": _count_by_key(sources, "source_group"),
            "scan_count": len(scans),
            "candidate_count": sum(int(item.get("candidate_count") or 0) for item in scans),
            "unique_candidate_domains": len(domains),
            "latest_scan": scans[-1] if scans else None,
        }

    def list_runs(self) -> list[dict[str, Any]]:
        self.ensure()
        if not self.index_path.exists():
            return [_run_summary(seeded_run())]
        try:
            items = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return [_run_summary(seeded_run())]
        if not isinstance(items, list):
            return [_run_summary(seeded_run())]
        return sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def save_run(self, run: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        clean_run = _strip_workflow(run)
        run_id = clean_run["id"]
        run_path = self.runs_dir / f"{run_id}.json"
        run_path.write_text(json.dumps(clean_run, indent=2, sort_keys=True), encoding="utf-8")

        index = [item for item in self.list_runs() if item.get("id") not in {run_id, SEED_RUN_ID}]
        index.append(_run_summary(clean_run))
        self.index_path.write_text(json.dumps(sorted(index, key=lambda item: str(item.get("created_at") or ""), reverse=True), indent=2, sort_keys=True), encoding="utf-8")
        return self.hydrate_run(clean_run)

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        self.ensure()
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            if run_id == SEED_RUN_ID:
                return self.hydrate_run(seeded_run())
            return None
        try:
            value = json.loads(run_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return self.hydrate_run(value) if isinstance(value, dict) else None

    def hydrate_run(self, run: dict[str, Any]) -> dict[str, Any]:
        hydrated = json.loads(json.dumps(run))
        run_id = str(hydrated.get("id") or "")
        states = self.load_lead_states(run_id)
        leads = hydrated.get("leads", [])
        if isinstance(leads, list):
            for lead in leads:
                if not isinstance(lead, dict):
                    continue
                domain = _lead_domain(lead)
                workflow = states.get(domain) or _default_lead_state(run_id, domain, _lead_company(lead))
                lead["workflow"] = workflow
        hydrated["workflow"] = {
            "lead_statuses": list(LEAD_STATUSES),
            "status_counts": self.lead_status_counts(run_id, hydrated),
            "saved_views": self.list_lead_views(),
        }
        return hydrated

    def load_lead_states(self, run_id: str | None = None) -> dict[str, dict[str, Any]]:
        self.ensure()
        payload = _load_json_file(self.lead_states_path, dict) or {}
        if run_id is None:
            return {
                str(item_run_id): value
                for item_run_id, value in payload.items()
                if isinstance(value, dict)
            }
        run_states = payload.get(run_id, {}) if isinstance(payload, dict) else {}
        return {
            _normalize_domain(domain): record
            for domain, record in run_states.items()
            if isinstance(record, dict)
        } if isinstance(run_states, dict) else {}

    def save_lead_state(
        self,
        run_id: str,
        domain: str,
        *,
        company: str = "",
        status: str | None = None,
        note: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        domain_key = _normalize_domain(domain)
        if not domain_key:
            raise ValueError("Lead domain is required.")
        payload = _load_json_file(self.lead_states_path, dict) or {}
        run_states = payload.setdefault(run_id, {})
        if not isinstance(run_states, dict):
            run_states = {}
            payload[run_id] = run_states
        existing = run_states.get(domain_key, {}) if isinstance(run_states.get(domain_key), dict) else {}
        previous_status = str(existing.get("status") or "New")
        next_status = _normalize_status(status or previous_status)
        now = now_iso()
        record = {
            "run_id": run_id,
            "domain": domain_key,
            "company": company or existing.get("company") or "",
            "status": next_status,
            "note": str(note if note is not None else existing.get("note", "")),
            "owner": str(owner if owner is not None else existing.get("owner", "")),
            "tags": _clean_tags(tags if tags is not None else existing.get("tags", [])),
            "created_at": str(existing.get("created_at") or now),
            "updated_at": now,
        }
        run_states[domain_key] = record
        self.lead_states_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "lead_state.updated",
            subject_type="lead",
            subject_id=f"{run_id}:{domain_key}",
            details={
                "run_id": run_id,
                "domain": domain_key,
                "company": record["company"],
                "previous_status": previous_status,
                "status": next_status,
            },
        )
        return record

    def bulk_update_lead_states(
        self,
        run_id: str,
        domains: list[str],
        *,
        status: str,
        note: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        updated = [
            self.save_lead_state(run_id, domain, status=status, note=note, owner=owner, tags=tags)
            for domain in domains
            if _normalize_domain(domain)
        ]
        return {
            "run_id": run_id,
            "updated_count": len(updated),
            "lead_states": updated,
            "status_counts": self.lead_status_counts(run_id),
        }

    def lead_status_counts(self, run_id: str, run: dict[str, Any] | None = None) -> dict[str, int]:
        counts = {status: 0 for status in LEAD_STATUSES}
        states = self.load_lead_states(run_id)
        seen_domains: set[str] = set()
        if run is None:
            raw = seeded_run() if run_id == SEED_RUN_ID else self._load_raw_run(run_id)
            run = raw if isinstance(raw, dict) else {"leads": []}
        leads = run.get("leads", []) if isinstance(run.get("leads"), list) else []
        for lead in leads:
            if not isinstance(lead, dict):
                continue
            domain = _lead_domain(lead)
            seen_domains.add(domain)
            status = states.get(domain, {}).get("status", "New")
            counts[_normalize_status(str(status))] += 1
        for domain, state in states.items():
            if domain not in seen_domains:
                counts[_normalize_status(str(state.get("status") or "New"))] += 1
        return counts

    def account_detail(self, run_id: str, account_key: str) -> dict[str, Any] | None:
        run = self.load_run(run_id)
        if not run:
            return None
        lead = _find_lead(run, account_key)
        if not lead:
            return None
        score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
        company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
        domain = _lead_domain(lead)
        strategy = lead.get("strategy", {}) if isinstance(lead.get("strategy"), dict) else {}
        metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
        evidence = [item for item in lead.get("evidence", []) if isinstance(item, dict)]
        prospects = build_lead_prospects(run, lead)
        workflow = lead.get("workflow") if isinstance(lead.get("workflow"), dict) else _default_lead_state(run_id, domain, _lead_company(lead))
        criteria = run.get("criteria", {}) if isinstance(run.get("criteria"), dict) else {}
        criteria_profile = criteria.get("profile") if isinstance(criteria.get("profile"), dict) else metadata.get("criteria_profile", {})
        quality_feedback = self.list_quality_feedback(run_id=run_id, domain=domain, limit=25)
        return {
            "run_id": run_id,
            "lead_id": lead.get("id"),
            "company": company,
            "score": score,
            "strategy": strategy,
            "workflow": workflow,
            "lead_statuses": list(LEAD_STATUSES),
            "prospects": prospects,
            "role_groups": _prospect_role_groups(prospects),
            "evidence_timeline": _evidence_timeline(evidence),
            "source_refs": metadata.get("source_refs", {}) if isinstance(metadata.get("source_refs"), dict) else {},
            "source_counts": metadata.get("source_counts", {}) if isinstance(metadata.get("source_counts"), dict) else {},
            "coverage": metadata.get("intelligence_coverage", {}) if isinstance(metadata.get("intelligence_coverage"), dict) else {},
            "criteria_snapshot": {
                "hash": criteria.get("hash") or criteria_profile.get("hash") or "",
                "source": criteria.get("source") or criteria_profile.get("source") or "",
                "profile": criteria_profile if isinstance(criteria_profile, dict) else {},
            },
            "quality_feedback": quality_feedback,
            "quality_summary": self.quality_feedback_summary(run_id=run_id, domain=domain),
            "audit_events": _audit_events_for_account(self.list_audit_events(limit=500), run_id, domain),
        }

    def save_quality_feedback(
        self,
        run_id: str,
        domain: str,
        *,
        company: str = "",
        dimension: str = "score",
        rating: str = "positive",
        note: str = "",
        target_id: str = "",
        target_label: str = "",
    ) -> dict[str, Any]:
        self.ensure()
        domain_key = _normalize_domain(domain)
        if not domain_key:
            raise ValueError("Lead domain is required.")
        clean_dimension = _normalize_quality_dimension(dimension)
        clean_rating = _normalize_quality_rating(rating)
        now = now_iso()
        events = self.list_quality_feedback(limit=1000)
        record = {
            "id": stable_hash(f"{now}:{run_id}:{domain_key}:{clean_dimension}:{clean_rating}:{target_id}:{len(events)}"),
            "run_id": run_id,
            "domain": domain_key,
            "company": " ".join(str(company).strip().split()),
            "dimension": clean_dimension,
            "rating": clean_rating,
            "target_id": str(target_id or ""),
            "target_label": " ".join(str(target_label).strip().split()),
            "note": str(note or "").strip(),
            "label_source": "operator_feedback",
            "k2_feedback_outcome": _quality_feedback_outcome(clean_rating),
            "created_at": now,
        }
        events.append(record)
        self.quality_feedback_path.write_text(json.dumps(events[-1000:], indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "quality_feedback.created",
            subject_type="quality_feedback",
            subject_id=f"{run_id}:{domain_key}:{clean_dimension}",
            details={
                "run_id": run_id,
                "domain": domain_key,
                "company": record["company"],
                "dimension": clean_dimension,
                "rating": clean_rating,
            },
        )
        return record

    def list_quality_feedback(
        self,
        *,
        run_id: str | None = None,
        domain: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.quality_feedback_path, list)
        events = [item for item in value or [] if isinstance(item, dict)]
        if run_id:
            events = [item for item in events if item.get("run_id") == run_id]
        if domain:
            domain_key = _normalize_domain(domain)
            events = [item for item in events if _normalize_domain(str(item.get("domain") or "")) == domain_key]
        return events[-max(1, min(limit, 1000)) :]

    def quality_feedback_summary(self, *, run_id: str | None = None, domain: str | None = None) -> dict[str, Any]:
        events = self.list_quality_feedback(run_id=run_id, domain=domain, limit=1000)
        rating_counts = {rating: 0 for rating in QUALITY_RATINGS}
        dimension_counts = {dimension: 0 for dimension in QUALITY_DIMENSIONS}
        for event in events:
            rating = _normalize_quality_rating(str(event.get("rating") or "neutral"))
            dimension = _normalize_quality_dimension(str(event.get("dimension") or "score"))
            rating_counts[rating] += 1
            dimension_counts[dimension] += 1
        total = len(events)
        return {
            "total": total,
            "rating_counts": rating_counts,
            "dimension_counts": dimension_counts,
            "positive_rate": round(rating_counts["positive"] / total, 4) if total else 0,
            "recent_feedback": events[-25:],
        }

    def quality_feedback_csv(self, *, run_id: str | None = None, domain: str | None = None) -> str:
        rows = self.list_quality_feedback(run_id=run_id, domain=domain, limit=1000)
        headers = [
            "id",
            "created_at",
            "run_id",
            "company",
            "domain",
            "dimension",
            "rating",
            "target_id",
            "target_label",
            "note",
            "label_source",
            "k2_feedback_outcome",
        ]
        lines = [",".join(headers)]
        for row in rows:
            lines.append(",".join(_csv_cell(row.get(header, "")) for header in headers))
        return "\n".join(lines) + "\n"

    def list_lead_views(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.lead_views_path, list)
        return [item for item in value or [] if isinstance(item, dict) and item.get("name")]

    def save_lead_view(
        self,
        name: str,
        *,
        filters: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        clean_name = " ".join(name.strip().split())
        if not clean_name:
            raise ValueError("View name is required.")
        now = now_iso()
        views = self.list_lead_views()
        view_id = stable_hash(clean_name.lower())
        previous = next((item for item in views if item.get("id") == view_id), {})
        view = {
            "id": view_id,
            "name": clean_name,
            "filters": filters if isinstance(filters, dict) else {},
            "sort": sort if isinstance(sort, dict) else {"field": "score", "direction": "desc"},
            "page_size": max(10, min(int(page_size or previous.get("page_size") or 50), 500)),
            "created_at": str(previous.get("created_at") or now),
            "updated_at": now,
        }
        next_views = [item for item in views if item.get("id") != view_id]
        next_views.append(view)
        self.lead_views_path.write_text(json.dumps(sorted(next_views, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "lead_view.saved",
            subject_type="lead_view",
            subject_id=view_id,
            details={"name": clean_name, "filters": view["filters"], "sort": view["sort"]},
        )
        return view

    def append_audit_event(
        self,
        action: str,
        *,
        subject_type: str,
        subject_id: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        events = self.list_audit_events(limit=500)
        event = {
            "id": stable_hash(f"{now_iso()}:{action}:{subject_type}:{subject_id}:{len(events)}"),
            "created_at": now_iso(),
            "action": action,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "details": details or {},
        }
        events.append(event)
        self.audit_log_path.write_text(json.dumps(events[-500:], indent=2, sort_keys=True), encoding="utf-8")
        return event

    def list_audit_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.audit_log_path, list)
        events = [item for item in value or [] if isinstance(item, dict)]
        return events[-max(1, min(limit, 500)) :]

    def provider_policy(self) -> dict[str, Any]:
        return _deep_merge_provider_limits(
            SEEDED_SETTINGS.get("provider_limits", {}),
            self.load_settings().get("provider_limits", {}),
        )

    def authorize_provider_action(
        self,
        action: str,
        *,
        amount: int = 1,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_action = _normalize_provider_action(action)
        clean_amount = max(1, int(amount or 1))
        clean_details = details if isinstance(details, dict) else {}
        policy = self.provider_policy()
        if not policy.get("enabled", True):
            event = self.record_provider_usage(
                clean_action,
                status="allowed",
                amount=clean_amount,
                details={**clean_details, "policy_disabled": True},
            )
            return {"allowed": True, "action": clean_action, "event": event, "policy": policy}
        denial = self._provider_action_denial(clean_action, clean_amount, clean_details, policy)
        if denial:
            event = self.record_provider_usage(
                clean_action,
                status="denied",
                amount=clean_amount,
                reason=denial["reason"],
                details=clean_details,
            )
            return {
                "allowed": False,
                "action": clean_action,
                "reason": denial["reason"],
                "event": event,
                "policy": policy,
                **denial,
            }
        event = self.record_provider_usage(
            clean_action,
            status="allowed",
            amount=clean_amount,
            details=clean_details,
        )
        return {"allowed": True, "action": clean_action, "event": event, "policy": policy}

    def record_provider_usage(
        self,
        action: str,
        *,
        status: str,
        amount: int = 1,
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        clean_action = _normalize_provider_action(action)
        now = now_iso()
        events = self.list_provider_usage(limit=1000)
        event = {
            "id": stable_hash(f"{now}:{clean_action}:{status}:{len(events)}"),
            "created_at": now,
            "action": clean_action,
            "status": status,
            "amount": max(1, int(amount or 1)),
            "reason": reason,
            "details": details or {},
        }
        events.append(event)
        self.provider_usage_path.write_text(
            json.dumps(events[-1000:], indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.append_audit_event(
            f"provider_action.{status}",
            subject_type="provider_action",
            subject_id=clean_action,
            details={
                "action": clean_action,
                "amount": event["amount"],
                "reason": reason,
                **(details or {}),
            },
        )
        return event

    def list_provider_usage(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.provider_usage_path, list)
        events = [item for item in value or [] if isinstance(item, dict)]
        return events[-max(1, min(limit, 1000)) :]

    def provider_usage_summary(self) -> dict[str, Any]:
        policy = self.provider_policy()
        events = self.list_provider_usage(limit=1000)
        today = now_iso()[:10]
        allowed_today = [
            event
            for event in events
            if str(event.get("created_at", "")).startswith(today)
            and event.get("status") == "allowed"
        ]
        denied_today = [
            event
            for event in events
            if str(event.get("created_at", "")).startswith(today)
            and event.get("status") == "denied"
        ]
        return {
            "policy": policy,
            "today": today,
            "allowed_counts": _provider_amounts_by_action(allowed_today),
            "denied_counts": _provider_amounts_by_action(denied_today),
            "recent_events": events[-25:],
        }

    def state(self) -> dict[str, Any]:
        runs = self.list_runs()
        summaries = [self._summary_with_workflow(item) for item in runs]
        latest_run = self.load_run(runs[0]["id"]) if runs else None
        return {
            "criteria": self.load_criteria(),
            "criteria_versions": self.list_criteria_versions(),
            "prompts": self.load_prompts(),
            "settings": self.load_settings(),
            "lists": self.load_lists(),
            "runs": summaries,
            "lead_statuses": list(LEAD_STATUSES),
            "lead_views": self.list_lead_views(),
            "sources": self.load_sources(),
            "source_scans": self.list_source_scans(limit=25),
            "source_coverage": self.source_coverage(),
            "provider_controls": self.provider_usage_summary(),
            "quality_feedback_summary": self.quality_feedback_summary(),
            "audit_log": self.list_audit_events(limit=25),
            "provider_status": provider_status(),
            "latest_run": latest_run,
        }

    def _provider_action_denial(
        self,
        action: str,
        amount: int,
        details: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any] | None:
        per_run = policy.get("per_run", {}) if isinstance(policy.get("per_run"), dict) else {}
        max_companies = int(details.get("max_companies") or 0)
        max_pages = int(details.get("max_pages") or 0)
        if (
            max_companies
            and int(per_run.get("max_companies") or 0)
            and max_companies > int(per_run["max_companies"])
        ):
            return {
                "reason": f"Requested max_companies={max_companies} exceeds provider policy max_companies={per_run['max_companies']}.",
                "limit_type": "per_run",
                "limit": int(per_run["max_companies"]),
                "usage": max_companies,
            }
        if (
            max_pages
            and int(per_run.get("max_pages") or 0)
            and max_pages > int(per_run["max_pages"])
        ):
            return {
                "reason": f"Requested max_pages={max_pages} exceeds provider policy max_pages={per_run['max_pages']}.",
                "limit_type": "per_run",
                "limit": int(per_run["max_pages"]),
                "usage": max_pages,
            }
        events = self.list_provider_usage(limit=1000)
        daily_limits = policy.get("daily", {}) if isinstance(policy.get("daily"), dict) else {}
        daily_limit = int(daily_limits.get(action) or 0)
        if daily_limit:
            usage = _provider_action_amount(
                [
                    event
                    for event in events
                    if _provider_event_is_today(event)
                    and event.get("action") == action
                    and event.get("status") == "allowed"
                ]
            )
            if usage + amount > daily_limit:
                return {
                    "reason": f"Daily provider budget for {action} is exhausted ({usage}/{daily_limit}, requested {amount}).",
                    "limit_type": "daily",
                    "limit": daily_limit,
                    "usage": usage,
                }
        rate_limits = policy.get("rate_per_minute", {}) if isinstance(policy.get("rate_per_minute"), dict) else {}
        rate_limit = int(rate_limits.get(action) or 0)
        if rate_limit:
            usage = _provider_action_amount(
                [
                    event
                    for event in events
                    if _provider_event_within_seconds(event, 60)
                    and event.get("action") == action
                    and event.get("status") == "allowed"
                ]
            )
            if usage + amount > rate_limit:
                return {
                    "reason": f"Rate limit for {action} is exceeded ({usage}/{rate_limit} in the last minute, requested {amount}).",
                    "limit_type": "rate_per_minute",
                    "limit": rate_limit,
                    "usage": usage,
                }
        return None

    def _load_raw_run(self, run_id: str) -> dict[str, Any] | None:
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            return None
        try:
            value = json.loads(run_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _summary_with_workflow(self, summary: dict[str, Any]) -> dict[str, Any]:
        run_id = str(summary.get("id") or "")
        return {
            **summary,
            "lead_status_counts": self.lead_status_counts(run_id),
            "quality_feedback_counts": self.quality_feedback_summary(run_id=run_id).get("rating_counts", {}),
        }

    def _criteria_history_with(self, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        value = _load_json_file(self.criteria_versions_path, list)
        history = [item for item in value or [] if isinstance(item, dict) and item.get("markdown")]
        return _append_unique_criteria_version(history, criteria)


def provider_status() -> dict[str, dict[str, Any]]:
    return {
        "apollo": {
            "configured": bool(os.environ.get("APOLLO_API_KEY")),
            "env": "APOLLO_API_KEY",
        },
        "k2": {
            "configured": bool(os.environ.get("K2_API_KEY")),
            "env": "K2_API_KEY",
            "base_url": os.environ.get("K2_BASE_URL", "https://api.knowledge2.ai"),
            "research_corpus_configured": bool(os.environ.get("K2_RESEARCH_CORPUS_ID")),
        },
        "github": {
            "configured": bool(os.environ.get("GITHUB_TOKEN")),
            "env": "GITHUB_TOKEN",
            "public_fallback": True,
        },
        "search": {
            "configured": True,
            "provider": os.environ.get(
                "ICP_SEARCH_PROVIDER",
                "serper" if os.environ.get("SERPER_API_KEY") or os.environ.get("SERP_API_KEY") else "duckduckgo-html",
            ),
            "serp_configured": bool(os.environ.get("SERPER_API_KEY") or os.environ.get("SERP_API_KEY")),
        },
    }


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    leads = run.get("leads", [])
    scores = [lead.get("score", {}).get("total_score", 0) for lead in leads]
    return {
        "id": run.get("id"),
        "query": run.get("query", ""),
        "created_at": run.get("created_at"),
        "status": run.get("status", "unknown"),
        "lead_count": len(leads),
        "top_score": max(scores) if scores else 0,
        "tier_counts": _tier_counts(leads),
        "warnings": run.get("warnings", [])[:5],
    }


def _tier_counts(leads: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lead in leads:
        tier = lead.get("score", {}).get("tier", "Unknown")
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _criteria_version(criteria: dict[str, Any]) -> dict[str, Any]:
    hash_value = str(criteria.get("hash") or stable_hash(str(criteria.get("markdown", ""))))
    return {
        "id": hash_value,
        "hash": hash_value,
        "markdown": str(criteria.get("markdown", "")),
        "source": str(criteria.get("source", "")),
        "updated_at": str(criteria.get("updated_at", "")),
    }


def _append_unique_criteria_version(history: list[dict[str, Any]], criteria: dict[str, Any]) -> list[dict[str, Any]]:
    version = _criteria_version(criteria)
    existing = [item for item in history if item.get("hash") != version["hash"]]
    existing.append(version)
    return existing[-50:]


def _load_json_file(path: Path, expected_type: type) -> Any | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, expected_type) else None


def _deep_merge_provider_limits(defaults: Any, overrides: Any) -> dict[str, Any]:
    base = json.loads(json.dumps(defaults if isinstance(defaults, dict) else {}))
    if not isinstance(overrides, dict):
        return base
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def _normalize_provider_action(action: str) -> str:
    return action.strip().lower().replace("-", "_").replace(" ", "_") or "unknown"


def _provider_amounts_by_action(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        action = _normalize_provider_action(str(event.get("action") or "unknown"))
        counts[action] = counts.get(action, 0) + int(event.get("amount") or 1)
    return counts


def _provider_action_amount(events: list[dict[str, Any]]) -> int:
    return sum(int(event.get("amount") or 1) for event in events)


def _provider_event_is_today(event: dict[str, Any]) -> bool:
    return str(event.get("created_at") or "").startswith(now_iso()[:10])


def _provider_event_within_seconds(event: dict[str, Any], seconds: int) -> bool:
    created_at = _parse_event_datetime(str(event.get("created_at") or ""))
    if not created_at:
        return False
    return (datetime.now(timezone.utc) - created_at).total_seconds() <= seconds


def _parse_event_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_sources() -> list[dict[str, Any]]:
    prompts = {item.get("id"): item for item in SEEDED_PROMPTS if isinstance(item, dict)}
    discovery_prompt = prompts.get("discovery-query", {})
    source_count = len(SEEDED_LISTS.get("account_universe", []))
    return [
        _source_seed_record(
            "seed-constellation-portfolio",
            name="Constellation/Volaris/Harris account universe",
            source_type="manual_seed",
            value=f"{source_count} committed portfolio and ICP accounts from local seed data",
            source_group="seeded-portfolio",
            schedule="manual",
            candidate_count=source_count,
        ),
        _source_seed_record(
            "seed-portfolio-expansion-serp",
            name="Portfolio expansion SERP",
            source_type="serp_query",
            value=str(discovery_prompt.get("text") or "vertical market software portfolio companies with workflow data"),
            source_group="portfolio-expansion",
            schedule="weekly",
        ),
        _source_seed_record(
            "seed-ai-gap-serp",
            name="AI gap audit SERP",
            source_type="serp_query",
            value="pre-2025 vertical SaaS workflow software weak AI positioning API integrations",
            source_group="ai-gap-audit",
            schedule="weekly",
        ),
    ]


def _source_seed_record(
    source_id: str,
    *,
    name: str,
    source_type: str,
    value: str,
    source_group: str,
    schedule: str,
    candidate_count: int = 0,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "name": name,
        "type": source_type,
        "value": value,
        "source_group": source_group,
        "schedule": schedule,
        "enabled": True,
        "created_at": "2026-06-13T00:00:00+00:00",
        "updated_at": "2026-06-13T00:00:00+00:00",
        "last_scan_at": "",
        "last_status": "seeded" if candidate_count else "never_scanned",
        "last_candidate_count": candidate_count,
        "last_warning_count": 0,
    }


def _normalize_source_record(item: dict[str, Any]) -> dict[str, Any]:
    source_type = _normalize_source_type(str(item.get("type") or "serp_query"))
    return {
        "id": str(item.get("id") or stable_hash(f"{source_type}:{item.get('name')}:{item.get('value')}")),
        "name": " ".join(str(item.get("name") or "Source").strip().split()),
        "type": source_type,
        "value": str(item.get("value") or "").strip(),
        "source_group": " ".join(str(item.get("source_group") or _source_group_for_type(source_type)).strip().split()),
        "schedule": _normalize_source_schedule(str(item.get("schedule") or "manual")),
        "enabled": bool(item.get("enabled", True)),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "last_scan_at": str(item.get("last_scan_at") or ""),
        "last_status": str(item.get("last_status") or "never_scanned"),
        "last_candidate_count": int(item.get("last_candidate_count") or 0),
        "last_warning_count": int(item.get("last_warning_count") or 0),
    }


def _normalize_source_type(source_type: str) -> str:
    normalized = source_type.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in SOURCE_TYPES:
        raise ValueError(f"Invalid source type: {source_type}. Expected one of {', '.join(SOURCE_TYPES)}.")
    return normalized


def _source_group_for_type(source_type: str) -> str:
    return {
        "serp_query": "saved-serp",
        "portfolio_url": "portfolio-page",
        "manual_seed": "manual-seed",
        "apollo_query": "apollo-search",
    }.get(source_type, "source")


def _normalize_source_schedule(schedule: str) -> str:
    normalized = schedule.strip().lower().replace("_", "-") or "manual"
    if normalized not in {"manual", "daily", "weekly", "monthly"} and not normalized.startswith("cron:"):
        raise ValueError("Source schedule must be manual, daily, weekly, monthly, or cron:<utc expression>.")
    return normalized


def _candidate_preview_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": str(item.get("company") or ""),
        "domain": _normalize_domain(str(item.get("domain") or "")),
        "source_url": str(item.get("source_url") or ""),
        "source_title": str(item.get("source_title") or ""),
        "notes": str(item.get("notes") or ""),
        "github_urls": [str(value) for value in item.get("github_urls", []) if value] if isinstance(item.get("github_urls"), list) else [],
        "linkedin_urls": [str(value) for value in item.get("linkedin_urls", []) if value] if isinstance(item.get("linkedin_urls"), list) else [],
        "other_urls": [str(value) for value in item.get("other_urls", []) if value] if isinstance(item.get("other_urls"), list) else [],
    }


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]


def _normalize_status(status: str) -> str:
    normalized = " ".join(status.strip().split()).title()
    if normalized not in LEAD_STATUSES:
        raise ValueError(f"Invalid lead status: {status}. Expected one of {', '.join(LEAD_STATUSES)}.")
    return normalized


def _normalize_quality_dimension(dimension: str) -> str:
    normalized = dimension.strip().lower().replace("-", "_").replace(" ", "_") or "score"
    if normalized not in QUALITY_DIMENSIONS:
        raise ValueError(f"Invalid feedback dimension: {dimension}. Expected one of {', '.join(QUALITY_DIMENSIONS)}.")
    return normalized


def _normalize_quality_rating(rating: str) -> str:
    normalized = rating.strip().lower().replace("-", "_").replace(" ", "_") or "neutral"
    if normalized in {"good", "yes", "useful", "correct"}:
        normalized = "positive"
    elif normalized in {"bad", "no", "wrong", "poor"}:
        normalized = "negative"
    if normalized not in QUALITY_RATINGS:
        raise ValueError(f"Invalid feedback rating: {rating}. Expected one of {', '.join(QUALITY_RATINGS)}.")
    return normalized


def _quality_feedback_outcome(rating: str) -> str:
    return {
        "positive": "accepted",
        "neutral": "needs_review",
        "negative": "rejected",
    }.get(rating, "needs_review")


def _csv_cell(value: Any) -> str:
    text = str(value if value is not None else "")
    escaped = text.replace('"', '""')
    return f'"{escaped}"' if any(char in escaped for char in [",", "\n", '"']) else escaped


def _clean_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    cleaned = []
    for tag in tags:
        value = " ".join(str(tag).strip().split())
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned[:20]


def _lead_domain(lead: dict[str, Any]) -> str:
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    return _normalize_domain(str(company.get("domain") or lead.get("domain") or "unknown"))


def _lead_company(lead: dict[str, Any]) -> str:
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    return str(company.get("company") or lead.get("company") or "")


def _find_lead(run: dict[str, Any], account_key: str) -> dict[str, Any] | None:
    key = _normalize_lookup_key(account_key)
    for lead in run.get("leads", []):
        if isinstance(lead, dict) and _lead_matches_key(lead, key):
            return lead
    return None


def _lead_matches_key(lead: dict[str, Any], key: str) -> bool:
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    candidates = [
        lead.get("id"),
        lead.get("domain"),
        lead.get("company"),
        company.get("domain"),
        company.get("company"),
    ]
    return key in {_normalize_lookup_key(str(item)) for item in candidates if item}


def _normalize_lookup_key(value: str) -> str:
    return _normalize_domain(value).removesuffix("/")


def _prospect_role_groups(prospects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for prospect in sorted(prospects, key=_prospect_sort_key):
        role = str(prospect.get("persona") or prospect.get("title") or "Other role")
        groups.setdefault(role, []).append(prospect)
    return [
        {
            "role": role,
            "priority": str(items[0].get("persona_priority") or items[0].get("source") or ""),
            "prospects": items,
        }
        for role, items in groups.items()
    ]


def _prospect_sort_key(prospect: dict[str, Any]) -> tuple[int, int, int, str]:
    priority_rank = {"primary": 0, "secondary": 1, "tertiary": 2}.get(str(prospect.get("persona_priority") or "").lower(), 3)
    source_rank = 0 if str(prospect.get("source") or "").lower() == "apollo" else 1
    score_rank = -int(prospect.get("priority_score") or 0)
    return (priority_rank, source_rank, score_rank, str(prospect.get("name") or prospect.get("title") or ""))


def _evidence_timeline(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline = []
    for index, item in enumerate(evidence, start=1):
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
        timeline.append(
            {
                "id": item.get("evidence_id") or f"evidence-{index}",
                "title": item.get("title") or item.get("url") or "Evidence",
                "url": item.get("url") or "",
                "text": item.get("text") or "",
                "source_type": item.get("source_type") or metadata.get("source_type") or metadata.get("page_category") or "website",
                "page_category": metadata.get("page_category") or "",
                "captured_at": item.get("captured_at") or metadata.get("captured_at") or "",
            }
        )
    return timeline


def _audit_events_for_account(events: list[dict[str, Any]], run_id: str, domain: str) -> list[dict[str, Any]]:
    subject_id = f"{run_id}:{domain}"
    matches = []
    for event in events:
        if event.get("subject_id") == subject_id:
            matches.append(event)
            continue
        details = event.get("details", {}) if isinstance(event.get("details"), dict) else {}
        if details.get("run_id") == run_id and _normalize_domain(str(details.get("domain") or "")) == domain:
            matches.append(event)
    return matches[-25:]


def _default_lead_state(run_id: str, domain: str, company: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "domain": domain,
        "company": company,
        "status": "New",
        "note": "",
        "owner": "",
        "tags": [],
        "created_at": "",
        "updated_at": "",
    }


def _strip_workflow(run: dict[str, Any]) -> dict[str, Any]:
    clean = json.loads(json.dumps(run))
    clean.pop("workflow", None)
    leads = clean.get("leads", [])
    if isinstance(leads, list):
        for lead in leads:
            if isinstance(lead, dict):
                lead.pop("workflow", None)
    return clean
