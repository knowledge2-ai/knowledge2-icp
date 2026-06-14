from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..criteria import build_criteria_profile
from ..criteria_editor import format_criteria_markdown, lint_criteria_markdown
from ..evals import (
    default_eval_cases,
    eval_runs_to_csv,
    normalize_eval_case,
    run_icp_evaluation,
    summarize_eval_runs,
)
from ..outreach import build_lead_outreach_drafts, normalize_outreach_status, outreach_drafts_to_csv, summarize_outreach_drafts
from ..prospects import build_lead_prospects
from ..seed_defaults import (
    SEEDED_CRITERIA_MARKDOWN,
    SEEDED_LISTS,
    SEEDED_PROMPTS,
    SEEDED_QUERY_PROFILES,
    SEEDED_SETTINGS,
    SEED_RUN_ID,
    seeded_run,
)

# Shared constants, public functions, and private helpers live in ``_helpers`` (the
# bottom of the package import DAG). The wildcard is deliberately broad for the
# mixin-extraction tasks; T9 narrows it to the names ``_core`` itself still uses.
from ._helpers import *  # noqa: F401,F403


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
        self.expansion_runs_path = self.state_dir / "expansion_runs.json"
        self.provider_usage_path = self.state_dir / "provider_usage.json"
        self.quality_feedback_path = self.state_dir / "quality_feedback.json"
        self.outreach_status_path = self.state_dir / "outreach_statuses.json"
        self.eval_cases_path = self.state_dir / "eval_cases.json"
        self.eval_runs_path = self.state_dir / "eval_runs.json"
        self.query_profiles_path = self.state_dir / "query_profiles.json"
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

    def criteria_impact(self, run_id: str, markdown: str) -> dict[str, Any]:
        run = self.load_run(run_id)
        if not run:
            raise ValueError("Run not found.")
        proposed_markdown = str(markdown or "")
        if not proposed_markdown.strip():
            raise ValueError("Criteria markdown is required.")
        proposed_profile = build_criteria_profile(
            proposed_markdown,
            source="criteria-impact-preview",
            criteria_hash=stable_hash(proposed_markdown),
        ).to_dict()
        current_profile = run.get("criteria", {}).get("profile")
        if not isinstance(current_profile, dict):
            criteria = self.load_criteria()
            current_profile = build_criteria_profile(
                str(criteria.get("markdown", "")),
                source=str(criteria.get("source", "")),
                criteria_hash=str(criteria.get("hash", "")),
            ).to_dict()
        leads = [lead for lead in run.get("leads", []) if isinstance(lead, dict)]
        changes: list[dict[str, Any]] = []
        current_counts = _tier_label_counts([str(lead.get("score", {}).get("tier") or "Unknown") for lead in leads])
        proposed_tiers: list[str] = []
        for lead in leads:
            score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
            company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
            current_tier = str(score.get("tier") or "Unknown")
            total_score = int(score.get("total_score") or 0)
            current_budget = int(score.get("budget_access_score") or 0)
            proposed_budget = _estimated_budget_score(company, proposed_profile, current_budget)
            proposed_total = max(0, min(100, total_score - current_budget + proposed_budget))
            proposed_tier = _tier_for_total(proposed_total, bool(score.get("hard_gate_failed")), proposed_profile)
            proposed_tiers.append(proposed_tier)
            if proposed_tier != current_tier or proposed_total != total_score:
                changes.append(
                    {
                        "company": str(company.get("company") or ""),
                        "domain": str(company.get("domain") or ""),
                        "current_tier": current_tier,
                        "proposed_tier": proposed_tier,
                        "current_score": total_score,
                        "proposed_score": proposed_total,
                        "score_delta": proposed_total - total_score,
                        "reason": _criteria_impact_reason(score, company, current_profile, proposed_profile, current_budget, proposed_budget),
                    }
                )
        proposed_counts = _tier_label_counts(proposed_tiers)
        warnings = list(proposed_profile.get("warnings") or [])
        if set(proposed_profile.get("priority_terms") or []) != set(current_profile.get("priority_terms") or []):
            warnings.append("Priority-term changes require a new run to fully re-score data/workflow boosts from evidence.")
        return {
            "run_id": run_id,
            "lead_count": len(leads),
            "current_profile": current_profile,
            "proposed_profile": proposed_profile,
            "lint": self.lint_criteria(proposed_markdown),
            "current_counts": current_counts,
            "proposed_counts": proposed_counts,
            "deltas": {tier: proposed_counts.get(tier, 0) - current_counts.get(tier, 0) for tier in ["A", "B", "C", "Reject", "Unknown"]},
            "changed_count": len(changes),
            "changes": sorted(changes, key=lambda item: (abs(int(item["score_delta"])), item["company"]), reverse=True)[:100],
            "warnings": warnings,
        }

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
        settings = {**SEEDED_SETTINGS, **value}
        settings["provider_limits"] = _deep_merge_provider_limits(
            SEEDED_SETTINGS.get("provider_limits", {}),
            settings.get("provider_limits", {}),
        )
        return settings

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        if not isinstance(payload, dict):
            raise ValueError("Settings payload must be an object.")
        current = self.load_settings()
        next_settings = deepcopy(current)
        for key in ("default_query", "employee_range"):
            if key in payload:
                next_settings[key] = " ".join(str(payload.get(key) or "").split())
        if "qualifier" in payload:
            qualifier = str(payload.get("qualifier") or "").strip().lower()
            if qualifier not in {"rules", "claude"}:
                raise ValueError("qualifier must be 'rules' or 'claude'.")
            next_settings["qualifier"] = qualifier
        if "discovery_provider" in payload:
            provider = str(payload.get("discovery_provider") or "").strip().lower()
            if provider not in {"auto", "perplexity", "serper", "duckduckgo"}:
                raise ValueError("discovery_provider must be 'auto', 'perplexity', 'serper', or 'duckduckgo'.")
            next_settings["discovery_provider"] = provider
        if "outreach_mode" in payload:
            outreach_mode = str(payload.get("outreach_mode") or "").strip().lower()
            if outreach_mode not in {"template", "claude"}:
                raise ValueError("outreach_mode must be 'template' or 'claude'.")
            next_settings["outreach_mode"] = outreach_mode
        if "mining_corpus" in payload:
            mining_corpus = str(payload.get("mining_corpus") or "").strip().lower()
            if mining_corpus not in {"auto", "candidate", "evidence", "prospect", "source", "criteria"}:
                raise ValueError("mining_corpus must be 'auto', 'candidate', 'evidence', 'prospect', 'source', or 'criteria'.")
            next_settings["mining_corpus"] = mining_corpus
        for key in ("fetch_website_evidence", "include_github_metadata", "use_apollo_enrichment", "use_serp_discovery"):
            if key in payload:
                next_settings[key] = _coerce_bool(payload[key], bool(current.get(key, False)))
        int_fields = {
            "max_companies": (1, 1000),
            "max_pages": (0, 100),
            "tier_a_threshold": (0, 100),
            "tier_b_threshold": (0, 100),
        }
        for key, (minimum, maximum) in int_fields.items():
            if key in payload:
                next_settings[key] = _bounded_int(payload[key], int(current.get(key) or minimum), minimum, maximum)
        if isinstance(payload.get("provider_limits"), dict):
            next_settings["provider_limits"] = _normalize_provider_limits(
                payload["provider_limits"],
                current.get("provider_limits", {}),
            )
        self.settings_path.write_text(json.dumps(next_settings, indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "settings.saved",
            subject_type="settings",
            subject_id="workspace",
            details={"keys": sorted(payload.keys())},
        )
        return self.load_settings()

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

    def list_expansion_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.expansion_runs_path, list)
        runs = [item for item in value or [] if isinstance(item, dict)]
        return runs[-max(1, min(limit, 500)) :]

    def expansion_sources_due(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        now_value = now or datetime.now(timezone.utc)
        return [
            source
            for source in self.load_sources()
            if source.get("enabled", True)
            and str(source.get("schedule") or "manual") != "manual"
            and _source_schedule_due(source, now_value)
        ]

    def record_expansion_run(
        self,
        *,
        trigger: str,
        status: str,
        source_results: list[dict[str, Any]],
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        self.ensure()
        now = now_iso()
        run = {
            "id": stable_hash(f"{now}:{trigger}:{len(source_results)}:{status}"),
            "created_at": now,
            "trigger": trigger,
            "status": status,
            "source_count": len(source_results),
            "scanned_source_count": sum(1 for item in source_results if item.get("status") != "skipped"),
            "candidate_count": sum(int(item.get("candidate_count") or 0) for item in source_results),
            "warning_count": sum(int(item.get("warning_count") or 0) for item in source_results) + len(warnings or []),
            "source_results": source_results[:100],
            "warnings": [str(item) for item in warnings or [] if str(item).strip()][:50],
        }
        runs = self.list_expansion_runs(limit=500)
        runs.append(run)
        self.expansion_runs_path.write_text(json.dumps(runs[-500:], indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "expansion.run",
            subject_type="expansion",
            subject_id=run["id"],
            details={"trigger": trigger, "status": status, "candidate_count": run["candidate_count"]},
        )
        return run

    def source_coverage(self) -> dict[str, Any]:
        sources = self.load_sources()
        scans = self.list_source_scans(limit=500)
        expansion_runs = self.list_expansion_runs(limit=25)
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
            "latest_expansion_run": expansion_runs[-1] if expansion_runs else None,
            "due_source_count": len(self.expansion_sources_due()),
        }

    def list_query_profiles(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.query_profiles_path, list)
        if value is None:
            return [deepcopy(item) for item in SEEDED_QUERY_PROFILES]
        return [item for item in value if isinstance(item, dict)]

    def save_query_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        if not isinstance(profile, dict):
            raise ValueError("Query profile payload must be an object.")
        name = " ".join(str(profile.get("name") or "").split())
        if not name:
            raise ValueError("Query profile name is required.")
        queries = [" ".join(str(item).split()) for item in profile.get("queries") or [] if str(item).strip()]
        filters = _clean_profile_filters(profile.get("filters"))
        now = now_iso()
        profile_id = str(profile.get("id") or "").strip() or stable_hash(f"{now}:{name.lower()}")
        existing = next((item for item in self.list_query_profiles() if item.get("id") == profile_id), {})
        record = {
            "id": profile_id,
            "name": name,
            "description": " ".join(str(profile.get("description") or "").split()),
            "queries": queries,
            "filters": filters,
            "created_at": str(existing.get("created_at") or now),
            "updated_at": now,
        }
        profiles = [item for item in self.list_query_profiles() if item.get("id") != profile_id]
        profiles.append(record)
        self.query_profiles_path.write_text(
            json.dumps(sorted(profiles, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.append_audit_event(
            "query_profile.saved",
            subject_type="query_profile",
            subject_id=profile_id,
            details={"name": name, "filter_count": len(filters), "query_count": len(queries)},
        )
        return record

    def delete_query_profile(self, profile_id: str) -> None:
        self.ensure()
        clean_id = str(profile_id or "").strip()
        if not clean_id:
            raise ValueError("Query profile id is required.")
        profiles = [item for item in self.list_query_profiles() if item.get("id") != clean_id]
        self.query_profiles_path.write_text(
            json.dumps(sorted(profiles, key=lambda item: str(item.get("name"))), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self.append_audit_event(
            "query_profile.deleted",
            subject_type="query_profile",
            subject_id=clean_id,
            details={},
        )

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
        outreach_drafts = self.list_outreach_drafts(run_id=run_id, domain=domain)
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
            "outreach_drafts": outreach_drafts,
            "outreach_summary": summarize_outreach_drafts(outreach_drafts),
            "audit_events": _audit_events_for_account(self.list_audit_events(limit=500), run_id, domain),
        }

    def list_outreach_drafts(self, *, run_id: str, domain: str | None = None) -> list[dict[str, Any]]:
        run = self.load_run(run_id)
        if not run:
            return []
        domain_key = _normalize_domain(domain or "")
        status_map = self.load_outreach_statuses(run_id)
        drafts: list[dict[str, Any]] = []
        for lead in run.get("leads", []):
            if not isinstance(lead, dict):
                continue
            if domain_key and _lead_domain(lead) != domain_key:
                continue
            drafts.extend(build_lead_outreach_drafts(run, lead, status_map))
        return drafts

    def load_outreach_statuses(self, run_id: str | None = None) -> dict[str, dict[str, Any]]:
        self.ensure()
        payload = _load_json_file(self.outreach_status_path, dict) or {}
        if run_id is None:
            merged: dict[str, dict[str, Any]] = {}
            for run_statuses in payload.values():
                if isinstance(run_statuses, dict):
                    merged.update({str(key): value for key, value in run_statuses.items() if isinstance(value, dict)})
            return merged
        run_statuses = payload.get(run_id, {}) if isinstance(payload, dict) else {}
        return {
            str(key): value
            for key, value in run_statuses.items()
            if isinstance(value, dict)
        } if isinstance(run_statuses, dict) else {}

    def save_outreach_status(
        self,
        run_id: str,
        prospect_id: str,
        *,
        domain: str = "",
        company: str = "",
        status: str = "Approved",
        note: str = "",
    ) -> dict[str, Any]:
        self.ensure()
        clean_prospect_id = str(prospect_id or "").strip()
        if not clean_prospect_id:
            raise ValueError("Prospect id is required.")
        clean_status = normalize_outreach_status(status)
        payload = _load_json_file(self.outreach_status_path, dict) or {}
        run_statuses = payload.setdefault(run_id, {})
        if not isinstance(run_statuses, dict):
            run_statuses = {}
            payload[run_id] = run_statuses
        existing = run_statuses.get(clean_prospect_id, {}) if isinstance(run_statuses.get(clean_prospect_id), dict) else {}
        now = now_iso()
        record = {
            "run_id": run_id,
            "prospect_id": clean_prospect_id,
            "domain": _normalize_domain(domain),
            "company": " ".join(str(company or existing.get("company") or "").strip().split()),
            "status": clean_status,
            "note": str(note if note is not None else existing.get("note", "")),
            "created_at": str(existing.get("created_at") or now),
            "updated_at": now,
        }
        run_statuses[clean_prospect_id] = record
        self.outreach_status_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "outreach_status.updated",
            subject_type="outreach_draft",
            subject_id=f"{run_id}:{clean_prospect_id}",
            details={
                "run_id": run_id,
                "prospect_id": clean_prospect_id,
                "domain": record["domain"],
                "company": record["company"],
                "status": clean_status,
            },
        )
        return record

    def outreach_summary(self, *, run_id: str | None = None) -> dict[str, Any]:
        if run_id:
            return summarize_outreach_drafts(self.list_outreach_drafts(run_id=run_id))
        summaries = [summarize_outreach_drafts(self.list_outreach_drafts(run_id=str(item.get("id") or ""))) for item in self.list_runs()]
        counts = {"Draft": 0, "Approved": 0, "Rejected": 0, "Exported": 0}
        total = 0
        for summary in summaries:
            total += int(summary.get("total") or 0)
            for status, count in summary.get("status_counts", {}).items():
                counts[status] = counts.get(status, 0) + int(count or 0)
        return {"total": total, "status_counts": counts, "ready_count": counts["Approved"] + counts["Exported"]}

    def outreach_drafts_csv(self, *, run_id: str, domain: str | None = None) -> str:
        return outreach_drafts_to_csv(self.list_outreach_drafts(run_id=run_id, domain=domain))

    def list_eval_cases(self, *, run_id: str | None = None) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.eval_cases_path, list)
        run = self.load_run(run_id) if run_id else None
        if value is None:
            return default_eval_cases(run)
        cases = []
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                cases.append(normalize_eval_case(item))
            except ValueError:
                continue
        return cases or default_eval_cases(run)

    def save_eval_case(self, case: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        normalized = normalize_eval_case(case)
        cases = [item for item in self.list_eval_cases() if item.get("id") != normalized["id"]]
        cases.append(normalized)
        self.eval_cases_path.write_text(json.dumps(sorted(cases, key=lambda item: str(item.get("id"))), indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "eval_case.saved",
            subject_type="eval_case",
            subject_id=normalized["id"],
            details={"type": normalized["type"], "domain": normalized["domain"], "label_source": normalized["label_source"]},
        )
        return normalized

    def run_eval(self, run_id: str, *, case_ids: list[str] | None = None) -> dict[str, Any]:
        self.ensure()
        run = self.load_run(run_id)
        if not run:
            raise ValueError("Run not found.")
        cases = self.list_eval_cases(run_id=run_id)
        if case_ids:
            selected = {str(case_id) for case_id in case_ids}
            cases = [case for case in cases if str(case.get("id")) in selected]
        result = run_icp_evaluation(
            run=run,
            cases=cases,
            quality_feedback=self.list_quality_feedback(run_id=run_id, limit=1000),
            outreach_drafts=self.list_outreach_drafts(run_id=run_id),
            source_coverage=self.source_coverage(),
            k2_status={"configured": provider_status()["k2"]["configured"], "base_url": provider_status()["k2"]["base_url"]},
        )
        runs = self.list_eval_runs(limit=500)
        runs.append(result)
        self.eval_runs_path.write_text(json.dumps(runs[-500:], indent=2, sort_keys=True), encoding="utf-8")
        self.append_audit_event(
            "eval_run.completed",
            subject_type="eval_run",
            subject_id=str(result.get("id") or ""),
            details={"run_id": run_id, "status": result.get("status"), "case_count": result.get("case_count")},
        )
        return result

    def list_eval_runs(self, *, run_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.eval_runs_path, list)
        runs = [item for item in value or [] if isinstance(item, dict)]
        if run_id:
            runs = [item for item in runs if item.get("run_id") == run_id]
        return runs[-max(1, min(limit, 500)) :]

    def eval_summary(self, *, run_id: str | None = None) -> dict[str, Any]:
        return summarize_eval_runs(self.list_eval_runs(run_id=run_id, limit=500))

    def eval_runs_csv(self, *, run_id: str | None = None) -> str:
        return eval_runs_to_csv(self.list_eval_runs(run_id=run_id, limit=500))

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
            "expansion_runs": self.list_expansion_runs(limit=25),
            "source_coverage": self.source_coverage(),
            "provider_controls": self.provider_usage_summary(),
            "quality_feedback_summary": self.quality_feedback_summary(),
            "outreach_summary": self.outreach_summary(),
            "eval_summary": self.eval_summary(),
            "audit_log": self.list_audit_events(limit=25),
            "provider_status": provider_status(),
            "workspace_state": self.workspace_state_status(),
            "latest_run": latest_run,
        }

    def workspace_state_status(self) -> dict[str, Any]:
        self.ensure()
        return {
            "durable": True,
            "store": "local-files",
            "state_dir": str(self.state_dir),
            "collections": [
                _local_collection_status("criteria", self.criteria_path, "object"),
                _local_collection_status("criteria_versions", self.criteria_versions_path, "array"),
                _local_collection_status("settings", self.settings_path, "object"),
                _local_collection_status("sources", self.sources_path, "array"),
                _local_collection_status("source_scans", self.source_scans_path, "array"),
                _local_collection_status("expansion_runs", self.expansion_runs_path, "array"),
                _local_collection_status("provider_usage", self.provider_usage_path, "array"),
                {
                    "key": "runs",
                    "persisted": self.index_path.exists(),
                    "count": len([item for item in self.list_runs() if item.get("id") != SEED_RUN_ID]),
                    "path": str(self.index_path),
                    "type": "array",
                },
                _local_collection_status("lead_states", self.lead_states_path, "object"),
                _local_collection_status("lead_views", self.lead_views_path, "array"),
                _local_collection_status("quality_feedback", self.quality_feedback_path, "array"),
                _local_collection_status("outreach_statuses", self.outreach_status_path, "object"),
                _local_collection_status("eval_cases", self.eval_cases_path, "array"),
                _local_collection_status("eval_runs", self.eval_runs_path, "array"),
            ],
            "warnings": [],
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
            "outreach_counts": self.outreach_summary(run_id=run_id).get("status_counts", {}),
            "eval_status": self.eval_summary(run_id=run_id).get("latest_status", "not_run"),
        }

    def _criteria_history_with(self, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        value = _load_json_file(self.criteria_versions_path, list)
        history = [item for item in value or [] if isinstance(item, dict) and item.get("markdown")]
        return _append_unique_criteria_version(history, criteria)
