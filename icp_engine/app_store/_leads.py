"""Leads cluster: runs, lead workflow state, status counts, and account detail."""

from __future__ import annotations

import json
from typing import Any

from ..outreach import summarize_outreach_drafts
from ..prospects import build_lead_prospects
from ..seed_defaults import SEED_RUN_ID, seeded_run
from ._helpers import (
    LEAD_STATUSES,
    _audit_events_for_account,
    _clean_tags,
    _coerce_lead_status,
    _default_lead_state,
    _evidence_timeline,
    _find_lead,
    _lead_company,
    _lead_domain,
    _load_json_file,
    _normalize_domain,
    _normalize_status,
    _prospect_role_groups,
    _run_summary,
    _strip_workflow,
    now_iso,
)


class LeadsMixin:
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
                str(item_run_id): {
                    domain: _sanitize_lead_state_record(record)
                    for domain, record in value.items()
                    if isinstance(record, dict)
                }
                for item_run_id, value in payload.items()
                if isinstance(value, dict)
            }
        run_states = payload.get(run_id, {}) if isinstance(payload, dict) else {}
        return {
            _normalize_domain(domain): _sanitize_lead_state_record(record)
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

    def _load_raw_run(self, run_id: str) -> dict[str, Any] | None:
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            return None
        try:
            value = json.loads(run_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


def _sanitize_lead_state_record(record: dict[str, Any]) -> dict[str, Any]:
    """Coerce a persisted lead-state record's status onto the enum so corrupt
    on-disk data degrades gracefully instead of raising downstream."""
    return {**record, "status": _coerce_lead_status(record.get("status"))}
