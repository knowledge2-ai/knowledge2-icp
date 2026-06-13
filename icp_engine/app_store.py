from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .criteria_editor import format_criteria_markdown, lint_criteria_markdown
from .seed_defaults import SEEDED_CRITERIA_MARKDOWN, SEEDED_LISTS, SEEDED_PROMPTS, SEEDED_SETTINGS, SEED_RUN_ID, seeded_run


DEFAULT_STATE_DIR = Path(os.environ.get("ICP_APP_STATE_DIR", "out/app_state"))
DEFAULT_ICP_PATH = Path(os.environ.get("ICP_CRITERIA_PATH", "icp.md"))
LEAD_STATUSES = ("New", "Review", "Qualified", "Rejected", "Exported")


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
            "audit_log": self.list_audit_events(limit=25),
            "provider_status": provider_status(),
            "latest_run": latest_run,
        }

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


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]


def _normalize_status(status: str) -> str:
    normalized = " ".join(status.strip().split()).title()
    if normalized not in LEAD_STATUSES:
        raise ValueError(f"Invalid lead status: {status}. Expected one of {', '.join(LEAD_STATUSES)}.")
    return normalized


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
