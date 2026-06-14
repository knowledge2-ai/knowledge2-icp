"""Engagement cluster: quality feedback, outreach drafts/statuses, and evals."""

from __future__ import annotations

import json
from typing import Any

from ..evals import (
    default_eval_cases,
    eval_runs_to_csv,
    normalize_eval_case,
    run_icp_evaluation,
    summarize_eval_runs,
)
from ..outreach import (
    build_lead_outreach_drafts,
    normalize_outreach_status,
    outreach_drafts_to_csv,
    summarize_outreach_drafts,
)
from ._helpers import (
    QUALITY_DIMENSIONS,
    QUALITY_RATINGS,
    _csv_cell,
    _lead_domain,
    _load_json_file,
    _normalize_domain,
    _normalize_quality_dimension,
    _normalize_quality_rating,
    _quality_feedback_outcome,
    now_iso,
    provider_status,
    stable_hash,
)


class EngagementMixin:
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
