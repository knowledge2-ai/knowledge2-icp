from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from .outreach import summarize_outreach_drafts
from .prospects import build_run_prospects


EVAL_CASE_TYPES = ("qualification", "data_load", "prospect_tree", "research", "outreach")
DEFAULT_EVAL_THRESHOLDS = {
    "required_metadata_completeness": 0.85,
    "evidence_coverage": 0.8,
    "qualification_case_pass_rate": 0.9,
    "prospect_role_coverage": 0.8,
    "outreach_draft_coverage": 0.8,
}
EVAL_RUN_CSV_FIELDS = [
    "id",
    "run_id",
    "status",
    "case_set_hash",
    "criteria_hash",
    "metric_name",
    "metric_value",
    "threshold",
    "passed",
]


def default_eval_cases(run: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    run_domains = {_lead_domain(lead) for lead in (run or {}).get("leads", []) if isinstance(lead, dict)}
    seed_cases = [
        {
            "id": "case-mojio-tier-a",
            "type": "qualification",
            "domain": "moj.io",
            "company": "Mojio",
            "expected": {"tier": "A", "hard_gate_failed": False},
            "label_source": "expert_labeled",
            "rationale": "Named ICP example with connected mobility workflow and telematics data.",
        },
        {
            "id": "case-automate-tier-a",
            "type": "qualification",
            "domain": "automate.co.za",
            "company": "Automate",
            "expected": {"tier": "A", "hard_gate_failed": False},
            "label_source": "expert_labeled",
            "rationale": "Named ICP/Volaris example with dealership workflow data.",
        },
        {
            "id": "case-servicetitan-tier-a",
            "type": "qualification",
            "domain": "servicetitan.com",
            "company": "ServiceTitan",
            "expected": {"tier": "A", "hard_gate_failed": False},
            "label_source": "seeded_gold",
            "rationale": "Qualified data-run account with field-service workflow depth.",
        },
        {
            "id": "case-ai-native-reject",
            "type": "qualification",
            "domain": "example.com",
            "company": "AI Native Example",
            "expected": {"tier": "Reject", "hard_gate_failed": True},
            "label_source": "negative_control",
            "rationale": "Seeded reject control for AI-native/too-new companies.",
        },
    ]
    if not run_domains:
        return [_eval_case(case) for case in seed_cases]
    present = [_eval_case(case) for case in seed_cases if _normalize_domain(case["domain"]) in run_domains]
    if present:
        return present
    return [
        _eval_case(
            {
                "id": "case-current-run-data-load",
                "type": "data_load",
                "domain": "",
                "company": "",
                "expected": {"min_leads": 1, "min_evidence_coverage": 0.8},
                "label_source": "bootstrap_generated",
                "rationale": "Bootstrap data-load coverage case for the active run.",
            }
        )
    ]


def normalize_eval_case(case: dict[str, Any]) -> dict[str, Any]:
    return _eval_case(case)


def run_icp_evaluation(
    *,
    run: dict[str, Any],
    cases: list[dict[str, Any]],
    quality_feedback: list[dict[str, Any]] | None = None,
    outreach_drafts: list[dict[str, Any]] | None = None,
    source_coverage: dict[str, Any] | None = None,
    k2_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now_iso()
    normalized_cases = [_eval_case(case) for case in cases]
    leads = [lead for lead in run.get("leads", []) if isinstance(lead, dict)]
    non_reject_leads = [lead for lead in leads if str(lead.get("score", {}).get("tier") or "") != "Reject"]
    domains = [_lead_domain(lead) for lead in leads]
    unique_domains = {domain for domain in domains if domain}
    duplicate_domains = sorted({domain for domain in unique_domains if domains.count(domain) > 1})
    prospects = build_run_prospects(run).get("prospects", [])
    outreach_drafts = outreach_drafts if outreach_drafts is not None else []
    quality_feedback = quality_feedback if quality_feedback is not None else []
    source_coverage = source_coverage if isinstance(source_coverage, dict) else {}
    qualification_results = _qualification_case_results(normalized_cases, leads)
    metrics = {
        "lead_count": len(leads),
        "non_reject_lead_count": len(non_reject_leads),
        "unique_domain_count": len(unique_domains),
        "duplicate_domain_count": len(duplicate_domains),
        "duplicate_domain_rate": _ratio(len(duplicate_domains), len(unique_domains)),
        "required_metadata_completeness": _required_metadata_completeness(leads),
        "evidence_coverage": _lead_coverage(leads, lambda lead: bool(lead.get("evidence"))),
        "citation_coverage": _lead_coverage(leads, _lead_has_citable_evidence),
        "qualification_case_pass_rate": _case_pass_rate(qualification_results),
        "qualification_case_count": len(qualification_results),
        "prospect_role_coverage": _prospect_role_coverage(non_reject_leads, prospects),
        "named_contact_rate": _prospect_rate(prospects, lambda prospect: bool(str(prospect.get("name") or "").strip()) and str(prospect.get("status") or "") == "person_found"),
        "contact_detail_rate": _prospect_rate(prospects, lambda prospect: any(prospect.get(key) for key in ("email", "phone", "linkedin_url"))),
        "outreach_draft_coverage": _outreach_draft_coverage(non_reject_leads, outreach_drafts),
        "outreach_ready_rate": _ratio(summarize_outreach_drafts(outreach_drafts).get("ready_count", 0), len(outreach_drafts)),
        "operator_feedback_count": len(quality_feedback),
        "operator_positive_rate": _operator_positive_rate(quality_feedback),
        "source_count": int(source_coverage.get("source_count") or 0),
        "source_scan_count": int(source_coverage.get("scan_count") or 0),
        "source_unique_candidate_domains": int(source_coverage.get("unique_candidate_domains") or 0),
    }
    checks = _threshold_checks(metrics)
    failures = _failures(leads, duplicate_domains, qualification_results, checks)
    status = "passed" if not failures else "needs_review"
    criteria = run.get("criteria", {}) if isinstance(run.get("criteria"), dict) else {}
    result = {
        "id": f"eval-{now.replace(':', '').replace('-', '')[:15]}-{_short_hash(run.get('id', 'run'))}",
        "run_id": run.get("id"),
        "status": status,
        "created_at": now,
        "case_set_hash": _short_hash(_stable_repr(normalized_cases)),
        "criteria_hash": str(criteria.get("hash") or ""),
        "case_count": len(normalized_cases),
        "metrics": metrics,
        "checks": checks,
        "case_results": qualification_results,
        "failures": failures[:100],
        "k2_alignment": {
            "system_of_record": "K2 quality/eval/feedback primitives when available",
            "primitives": ["EvalRun", "GoldLabel", "Feedback", "QualityMetrics", "Metadata", "Feeds", "Agents"],
            "native_eval_status": _k2_native_eval_status(k2_status),
        },
        "oss_adapters": _oss_adapter_status(),
    }
    return result


def summarize_eval_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(runs, key=lambda item: str(item.get("created_at") or ""))
    latest = ordered[-1] if ordered else None
    status_counts: dict[str, int] = {}
    for run in runs:
        status = str(run.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "total": len(runs),
        "status_counts": status_counts,
        "latest_run": latest,
        "latest_status": latest.get("status") if latest else "not_run",
        "latest_metrics": latest.get("metrics", {}) if latest else {},
        "latest_failures": latest.get("failures", [])[:10] if latest else [],
    }


def eval_runs_to_csv(runs: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EVAL_RUN_CSV_FIELDS)
    writer.writeheader()
    for run in runs:
        metrics = run.get("metrics", {}) if isinstance(run.get("metrics"), dict) else {}
        checks = run.get("checks", {}) if isinstance(run.get("checks"), dict) else {}
        for name, value in metrics.items():
            check = checks.get(name, {}) if isinstance(checks.get(name), dict) else {}
            writer.writerow(
                {
                    "id": run.get("id", ""),
                    "run_id": run.get("run_id", ""),
                    "status": run.get("status", ""),
                    "case_set_hash": run.get("case_set_hash", ""),
                    "criteria_hash": run.get("criteria_hash", ""),
                    "metric_name": name,
                    "metric_value": value,
                    "threshold": check.get("threshold", ""),
                    "passed": check.get("passed", ""),
                }
            )
    return output.getvalue()


def _eval_case(case: dict[str, Any]) -> dict[str, Any]:
    case_type = str(case.get("type") or "qualification").strip().lower().replace("-", "_")
    if case_type not in EVAL_CASE_TYPES:
        raise ValueError(f"Invalid eval case type: {case_type}.")
    return {
        "id": str(case.get("id") or _short_hash(_stable_repr(case))),
        "type": case_type,
        "domain": _normalize_domain(case.get("domain", "")),
        "company": " ".join(str(case.get("company") or "").split()),
        "expected": case.get("expected") if isinstance(case.get("expected"), dict) else {},
        "criteria_hash": str(case.get("criteria_hash") or ""),
        "label_source": str(case.get("label_source") or "bootstrap_generated"),
        "rationale": str(case.get("rationale") or ""),
        "created_at": str(case.get("created_at") or _now_iso()),
    }


def _qualification_case_results(cases: list[dict[str, Any]], leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    by_domain = {_lead_domain(lead): lead for lead in leads}
    for case in cases:
        if case.get("type") != "qualification":
            continue
        lead = by_domain.get(_normalize_domain(case.get("domain", "")))
        expected = case.get("expected", {}) if isinstance(case.get("expected"), dict) else {}
        actual_score = lead.get("score", {}) if isinstance(lead, dict) and isinstance(lead.get("score"), dict) else {}
        actual_tier = str(actual_score.get("tier") or "")
        actual_gate_failed = bool(actual_score.get("hard_gate_failed"))
        expected_tier = str(expected.get("tier") or "")
        expected_gate_failed = expected.get("hard_gate_failed")
        passed = bool(lead)
        if expected_tier:
            passed = passed and actual_tier == expected_tier
        if expected_gate_failed is not None:
            passed = passed and actual_gate_failed is bool(expected_gate_failed)
        results.append(
            {
                "case_id": case.get("id"),
                "domain": case.get("domain"),
                "company": case.get("company"),
                "passed": passed,
                "expected": expected,
                "actual": {
                    "tier": actual_tier if lead else "",
                    "hard_gate_failed": actual_gate_failed if lead else None,
                    "total_score": actual_score.get("total_score") if lead else None,
                },
                "reason": "matched" if passed else "expected qualification did not match produced lead",
            }
        )
    return results


def _threshold_checks(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    for name, threshold in DEFAULT_EVAL_THRESHOLDS.items():
        if name == "qualification_case_pass_rate" and not metrics.get("qualification_case_count"):
            checks[name] = {"threshold": threshold, "passed": True, "skipped": True, "reason": "No qualification cases matched this run."}
            continue
        value = float(metrics.get(name) or 0)
        checks[name] = {"threshold": threshold, "passed": value >= threshold, "value": value}
    return checks


def _failures(
    leads: list[dict[str, Any]],
    duplicate_domains: list[str],
    qualification_results: list[dict[str, Any]],
    checks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for name, check in checks.items():
        if not check.get("passed"):
            failures.append({"type": "metric_threshold", "metric": name, "value": check.get("value"), "threshold": check.get("threshold")})
    for domain in duplicate_domains:
        failures.append({"type": "duplicate_domain", "domain": domain})
    for result in qualification_results:
        if not result.get("passed"):
            failures.append({"type": "qualification_case", **result})
    for lead in leads:
        if not _lead_has_citable_evidence(lead):
            failures.append({"type": "missing_citable_evidence", "lead_id": lead.get("id"), "domain": _lead_domain(lead)})
    return failures


def _required_metadata_completeness(leads: list[dict[str, Any]]) -> float:
    required = [
        lambda lead: bool(lead.get("id")),
        lambda lead: bool(lead.get("score", {}).get("company", {}).get("company")),
        lambda lead: bool(lead.get("score", {}).get("company", {}).get("domain")),
        lambda lead: bool(lead.get("score", {}).get("tier")),
        lambda lead: lead.get("score", {}).get("total_score") is not None,
        lambda lead: bool(lead.get("strategy", {}).get("outreach_angle")),
        lambda lead: bool(lead.get("strategy", {}).get("personas")),
        lambda lead: bool(lead.get("metadata", {}).get("criteria_profile") or lead.get("metadata", {}).get("qualification")),
        lambda lead: bool(lead.get("evidence")),
    ]
    if not leads:
        return 0
    checks = sum(1 for lead in leads for predicate in required if predicate(lead))
    return round(checks / (len(leads) * len(required)), 4)


def _lead_coverage(leads: list[dict[str, Any]], predicate) -> float:
    return _ratio(sum(1 for lead in leads if predicate(lead)), len(leads))


def _lead_has_citable_evidence(lead: dict[str, Any]) -> bool:
    for item in lead.get("evidence", []):
        if isinstance(item, dict) and item.get("url") and (item.get("text") or item.get("title")):
            return True
    return False


def _case_pass_rate(results: list[dict[str, Any]]) -> float:
    return _ratio(sum(1 for result in results if result.get("passed")), len(results))


def _prospect_role_coverage(leads: list[dict[str, Any]], prospects: list[dict[str, Any]]) -> float:
    if not leads:
        return 1
    prospect_lead_ids = {str(item.get("lead_id") or "") for item in prospects if item.get("persona") or item.get("title")}
    return _ratio(sum(1 for lead in leads if str(lead.get("id") or "") in prospect_lead_ids), len(leads))


def _prospect_rate(prospects: list[dict[str, Any]], predicate) -> float:
    return _ratio(sum(1 for prospect in prospects if predicate(prospect)), len(prospects))


def _outreach_draft_coverage(leads: list[dict[str, Any]], drafts: list[dict[str, Any]]) -> float:
    if not leads:
        return 1
    lead_ids = {str(draft.get("lead_id") or "") for draft in drafts}
    return _ratio(sum(1 for lead in leads if str(lead.get("id") or "") in lead_ids), len(leads))


def _operator_positive_rate(events: list[dict[str, Any]]) -> float:
    return _ratio(sum(1 for event in events if str(event.get("rating") or "") == "positive"), len(events))


def _k2_native_eval_status(k2_status: dict[str, Any] | None) -> dict[str, Any]:
    if not k2_status:
        return {
            "status": "not_configured",
            "reason": "K2 native EvalRun creation is feature-gated/internal in current K2 dev docs; local ICP eval remains canonical for this app slice.",
        }
    return k2_status


def _oss_adapter_status() -> dict[str, dict[str, Any]]:
    return {
        "langfuse": {
            "enabled": False,
            "status": "not_configured",
            "reason": "Optional trace/eval adapter. K2 remains the system of record for quality state.",
        },
        "phoenix": {
            "enabled": False,
            "status": "not_configured",
            "reason": "Optional OSS observability adapter for traces and LLM judge experiments.",
        },
    }


def _lead_domain(lead: dict[str, Any]) -> str:
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    return _normalize_domain(company.get("domain") or lead.get("domain") or "")


def _normalize_domain(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return text.split("/")[0]


def _ratio(numerator: object, denominator: object) -> float:
    try:
        bottom = float(denominator)
        if bottom <= 0:
            return 0
        return round(float(numerator) / bottom, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


def _short_hash(value: object) -> str:
    import hashlib

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _stable_repr(value: object) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
