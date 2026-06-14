"""Module-level helpers, constants, and pure functions shared by the AppStore mixins.

This module imports only stdlib + sibling ``icp_engine.*`` modules — never ``_core`` or
any mixin — so it sits at the bottom of the package's import DAG.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..mining import MINING_FILTER_KEYS, MINING_FILTER_OPS
from ..seed_defaults import SEEDED_LISTS, SEEDED_PROMPTS, SEEDED_SETTINGS


DEFAULT_STATE_DIR = Path(os.environ.get("ICP_APP_STATE_DIR", "out/app_state"))
DEFAULT_ICP_PATH = Path(os.environ.get("ICP_CRITERIA_PATH", "icp.md"))
LEAD_STATUSES = ("New", "Review", "Qualified", "Rejected", "Exported")
SOURCE_TYPES = ("serp_query", "portfolio_url", "manual_seed", "csv_upload", "apollo_query")
QUALITY_DIMENSIONS = ("score", "persona", "outreach")
QUALITY_RATINGS = ("positive", "neutral", "negative")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


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


def _clean_profile_filters(raw: Any) -> list[dict[str, Any]]:
    """Validate query-profile filter clauses against the standardized mining keys/ops."""
    filters: list[dict[str, Any]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            raise ValueError("Each query-profile filter must be an object.")
        key = str(item.get("key") or "").strip()
        op = str(item.get("op") or "==").strip()
        if key not in MINING_FILTER_KEYS:
            raise ValueError(f"Unsupported query-profile filter key: {key!r}")
        if op not in MINING_FILTER_OPS:
            raise ValueError(f"Unsupported query-profile filter op: {op!r}")
        filters.append({"key": key, "op": op, "value": item.get("value")})
    return filters


def _load_json_file(path: Path, expected_type: type) -> Any | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, expected_type) else None


def _local_collection_status(key: str, path: Path, expected: str) -> dict[str, Any]:
    expected_type = list if expected == "array" else dict
    value = _load_json_file(path, expected_type)
    if expected == "object" and key == "criteria" and path.exists():
        count = 1
    elif isinstance(value, list):
        count = len(value)
    elif isinstance(value, dict):
        count = len(value)
    else:
        count = 0
    return {
        "key": key,
        "persisted": path.exists(),
        "count": count,
        "path": str(path),
        "type": expected,
    }


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


def _normalize_provider_limits(payload: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    limits = _deep_merge_provider_limits(SEEDED_SETTINGS.get("provider_limits", {}), current)
    if "enabled" in payload:
        limits["enabled"] = _coerce_bool(payload["enabled"], bool(limits.get("enabled", True)))
    for group in ("daily", "rate_per_minute"):
        values = payload.get(group)
        if not isinstance(values, dict):
            continue
        current_group = limits.get(group, {}) if isinstance(limits.get(group), dict) else {}
        limits[group] = {
            **current_group,
            **{
                str(key): _bounded_int(value, int(current_group.get(str(key), 0) or 0), 0, 100000)
                for key, value in values.items()
            },
        }
    per_run = payload.get("per_run")
    if isinstance(per_run, dict):
        current_per_run = limits.get("per_run", {}) if isinstance(limits.get("per_run"), dict) else {}
        limits["per_run"] = {
            **current_per_run,
            **{
                str(key): _bounded_int(value, int(current_per_run.get(str(key), 0) or 0), 0, 10000)
                for key, value in per_run.items()
            },
        }
    return _deep_merge_provider_limits(SEEDED_SETTINGS.get("provider_limits", {}), limits)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected an integer between {minimum} and {maximum}.") from exc
    return max(minimum, min(number, maximum))


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _tier_label_counts(tiers: list[str]) -> dict[str, int]:
    counts = {tier: 0 for tier in ["A", "B", "C", "Reject", "Unknown"]}
    for tier in tiers:
        counts[tier if tier in counts else "Unknown"] += 1
    return counts


def _tier_for_total(total_score: int, hard_gate_failed: bool, profile: dict[str, Any]) -> str:
    if hard_gate_failed:
        return "Reject"
    if total_score >= int(profile.get("tier_a_threshold") or 75):
        return "A"
    if total_score >= int(profile.get("tier_b_threshold") or 60):
        return "B"
    return "C"


def _estimated_budget_score(company: dict[str, Any], profile: dict[str, Any], fallback: int) -> int:
    employee_count = company.get("employee_count")
    if employee_count is None:
        return fallback
    try:
        employees = int(employee_count)
    except (TypeError, ValueError):
        return fallback
    minimum = int(profile.get("min_employee_count") or 25)
    maximum = int(profile.get("max_employee_count") or 2000)
    if minimum <= employees <= maximum:
        return 5
    if employees > maximum:
        return 4
    return 2


def _criteria_impact_reason(
    score: dict[str, Any],
    company: dict[str, Any],
    current_profile: dict[str, Any],
    proposed_profile: dict[str, Any],
    current_budget: int,
    proposed_budget: int,
) -> str:
    reasons: list[str] = []
    if current_profile.get("tier_a_threshold") != proposed_profile.get("tier_a_threshold"):
        reasons.append(f"Tier A threshold {current_profile.get('tier_a_threshold')} -> {proposed_profile.get('tier_a_threshold')}.")
    if current_profile.get("tier_b_threshold") != proposed_profile.get("tier_b_threshold"):
        reasons.append(f"Tier B threshold {current_profile.get('tier_b_threshold')} -> {proposed_profile.get('tier_b_threshold')}.")
    if current_budget != proposed_budget:
        reasons.append(
            f"Budget score {current_budget} -> {proposed_budget} from employee range "
            f"{proposed_profile.get('min_employee_count')}-{proposed_profile.get('max_employee_count')} and "
            f"{company.get('employee_count') or 'unknown'} employees."
        )
    if score.get("hard_gate_failed"):
        reasons.append("Hard gate failure still forces Reject.")
    return " ".join(reasons) or "Tier changed from updated thresholds."


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
        "csv_upload": "csv-upload",
        "apollo_query": "apollo-search",
    }.get(source_type, "source")


def _normalize_source_schedule(schedule: str) -> str:
    normalized = schedule.strip().lower().replace("_", "-") or "manual"
    if normalized not in {"manual", "daily", "weekly", "monthly"} and not normalized.startswith("cron:"):
        raise ValueError("Source schedule must be manual, daily, weekly, monthly, or cron:<utc expression>.")
    return normalized


def _source_schedule_due(source: dict[str, Any], now: datetime) -> bool:
    schedule = str(source.get("schedule") or "manual")
    if schedule == "manual":
        return False
    last_scan = _parse_event_datetime(str(source.get("last_scan_at") or ""))
    if last_scan is None:
        return True
    intervals = {
        "daily": 24 * 60 * 60,
        "weekly": 7 * 24 * 60 * 60,
        "monthly": 30 * 24 * 60 * 60,
    }
    if schedule.startswith("cron:"):
        return False
    interval = intervals.get(schedule)
    return bool(interval and (now - last_scan).total_seconds() >= interval)


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


__all__ = [
    "DEFAULT_STATE_DIR",
    "DEFAULT_ICP_PATH",
    "LEAD_STATUSES",
    "SOURCE_TYPES",
    "QUALITY_DIMENSIONS",
    "QUALITY_RATINGS",
    "now_iso",
    "stable_hash",
    "provider_status",
    "_run_summary",
    "_tier_counts",
    "_criteria_version",
    "_append_unique_criteria_version",
    "_clean_profile_filters",
    "_load_json_file",
    "_local_collection_status",
    "_deep_merge_provider_limits",
    "_normalize_provider_limits",
    "_bounded_int",
    "_coerce_bool",
    "_tier_label_counts",
    "_tier_for_total",
    "_estimated_budget_score",
    "_criteria_impact_reason",
    "_normalize_provider_action",
    "_provider_amounts_by_action",
    "_provider_action_amount",
    "_provider_event_is_today",
    "_provider_event_within_seconds",
    "_parse_event_datetime",
    "_default_sources",
    "_source_seed_record",
    "_normalize_source_record",
    "_normalize_source_type",
    "_source_group_for_type",
    "_normalize_source_schedule",
    "_source_schedule_due",
    "_candidate_preview_record",
    "_count_by_key",
    "_normalize_domain",
    "_normalize_status",
    "_normalize_quality_dimension",
    "_normalize_quality_rating",
    "_quality_feedback_outcome",
    "_csv_cell",
    "_clean_tags",
    "_lead_domain",
    "_lead_company",
    "_find_lead",
    "_lead_matches_key",
    "_normalize_lookup_key",
    "_prospect_role_groups",
    "_prospect_sort_key",
    "_evidence_timeline",
    "_audit_events_for_account",
    "_default_lead_state",
    "_strip_workflow",
]
