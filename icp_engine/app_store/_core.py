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
from ._config import ConfigMixin
from ._criteria import CriteriaMixin
from ._leads import LeadsMixin
from ._sources import SourcesMixin
from ._helpers import *  # noqa: F401,F403


class AppStore(CriteriaMixin, ConfigMixin, LeadsMixin, SourcesMixin):
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

    def _summary_with_workflow(self, summary: dict[str, Any]) -> dict[str, Any]:
        run_id = str(summary.get("id") or "")
        return {
            **summary,
            "lead_status_counts": self.lead_status_counts(run_id),
            "quality_feedback_counts": self.quality_feedback_summary(run_id=run_id).get("rating_counts", {}),
            "outreach_counts": self.outreach_summary(run_id=run_id).get("status_counts", {}),
            "eval_status": self.eval_summary(run_id=run_id).get("latest_status", "not_run"),
        }
