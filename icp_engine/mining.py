from __future__ import annotations

import csv
import io
from typing import Any

from .enrichment import normalize_domain

# The standardized metadata keys (PRD §14.3) that K2 search/subscription match specs
# operate on across the ICP corpora. The mining filter seam (and saved query profiles)
# only accept these keys so a query can't be fed fields the corpora never declared.
MINING_FILTER_KEYS: frozenset[str] = frozenset(
    {
        "run_id",
        "entity_type",
        "company",
        "domain",
        "vertical",
        "source_group",
        "portfolio_parent",
        "source_type",
        "source_url",
        "discovery_query",
        "criteria_hash",
        "criteria_version",
        "tier",
        "total_score",
        "ai_posture",
        "ai_gap_score",
        "data_workflow_score",
        "commercial_urgency_score",
        "budget_access_score",
        "feasibility_score",
        "hard_gate_failed",
        "hard_gate_unknown",
        "has_contact_path",
        "has_docs_or_api",
        "has_pricing_or_commercial",
        "prospect_name",
        "prospect_title",
        "persona_title",
        "persona_priority",
        "contact_confidence",
        "outreach_status",
        "feed_id",
        "feed_run_at",
        "pipeline_run_id",
    }
)

MINING_FILTER_OPS: frozenset[str] = frozenset({"==", "!=", ">", ">=", "<", "<=", "in", "contains"})

# Facet dimensions and CSV layout shared by the live K2 path and the local fallback,
# so both surfaces (and the CSV export) speak one shape regardless of provider.
FACET_KEYS: tuple[str, ...] = ("tier", "ai_posture", "vertical")

MINING_CSV_FIELDS: list[str] = [
    "company",
    "domain",
    "vertical",
    "tier",
    "ai_posture",
    "total_score",
    "outreach_status",
    "run_id",
    "snippet",
]

# Record fields the in-memory miner can actually evaluate. A filter clause on any
# other (still-valid §14.3) key is skipped offline with a warning rather than
# silently dropping every record.
_LOCAL_FIELDS: frozenset[str] = frozenset(
    {"company", "domain", "vertical", "tier", "ai_posture", "total_score", "outreach_status"}
)


def normalize_clauses(filters: Any) -> list[tuple[str, str, Any]]:
    """Coerce filter input (list of dicts or tuples) into ``(key, op, value)`` tuples."""
    clauses: list[tuple[str, str, Any]] = []
    for item in filters or []:
        if isinstance(item, dict):
            key = str(item.get("key") or "").strip()
            op = str(item.get("op") or "==").strip()
            clauses.append((key, op, item.get("value")))
        elif isinstance(item, (list, tuple)) and len(item) == 3:
            clauses.append((str(item[0]).strip(), str(item[1]).strip(), item[2]))
    return clauses


def shape_record(
    metadata: dict[str, Any],
    *,
    snippet: str = "",
    citations: list[str] | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    return {
        "company": str(metadata.get("company") or ""),
        "domain": normalize_domain(str(metadata.get("domain") or "")),
        "vertical": str(metadata.get("vertical") or ""),
        "tier": str(metadata.get("tier") or ""),
        "ai_posture": str(metadata.get("ai_posture") or ""),
        "total_score": metadata.get("total_score"),
        "outreach_status": str(metadata.get("outreach_status") or ""),
        "snippet": snippet.strip()[:280].replace("\n", " "),
        "citations": [str(url) for url in (citations or []) if str(url).strip()][:6],
        "run_id": str(metadata.get("run_id") or run_id or ""),
    }


def build_facets(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    facets: dict[str, dict[str, int]] = {key: {} for key in FACET_KEYS}
    for result in results:
        for key in FACET_KEYS:
            value = str(result.get(key) or "").strip()
            if not value:
                continue
            facets[key][value] = facets[key].get(value, 0) + 1
    return facets


def shape_live_results(payload: dict[str, Any], *, top_k: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in _search_items(payload):
        metadata = _result_metadata(item)
        results.append(
            shape_record(
                metadata,
                snippet=_result_snippet(item),
                citations=_result_citations(item, metadata),
            )
        )
    return results[: max(1, top_k)]


def mine_local(
    store: Any,
    *,
    query: str,
    clauses: list[tuple[str, str, Any]],
    corpus_key: str = "candidate",
    top_k: int = 20,
) -> dict[str, Any]:
    """Mine already-persisted runs in memory when K2 is unconfigured or down.

    Loads leads across every saved run, applies the same metadata clauses the live
    path would (the ones evaluable offline), ranks by query-token overlap then score,
    and rolls up the same facets. Never raises.
    """
    warnings: list[str] = []
    unevaluable = sorted({key for key, _, _ in clauses if key not in _LOCAL_FIELDS})
    if unevaluable:
        warnings.append("Filters not available offline were skipped: " + ", ".join(unevaluable) + ".")

    records = _load_lead_records(store)
    matched = [record for record in records if _matches_clauses(record, clauses)]
    ranked = _rank_by_query(matched, query)[: max(1, top_k)]
    warnings.insert(0, f"K2 not configured; mined {len(records)} persisted lead(s) in-memory.")
    return {
        "provider": "local",
        "corpus": corpus_key,
        "results": ranked,
        "facets": build_facets(ranked),
        "warnings": warnings,
    }


def lookalikes_local(
    store: Any,
    *,
    seed_domains: list[str],
    corpus_key: str = "candidate",
    top_k: int = 20,
) -> dict[str, Any]:
    """Rank persisted non-seed leads by shared ICP features against the seed accounts."""
    seeds = {normalize_domain(domain) for domain in seed_domains if normalize_domain(domain)}
    if not seeds:
        return {"provider": "local", "corpus": corpus_key, "results": [], "facets": {}, "warnings": ["No seed domains supplied."]}

    records = _load_lead_records(store)
    seed_records = [record for record in records if record["domain"] in seeds]
    profile = _seed_profile(seed_records)
    candidates = [record for record in records if record["domain"] not in seeds]
    scored = sorted(
        candidates,
        key=lambda record: (_lookalike_score(record, profile), _score_value(record.get("total_score"))),
        reverse=True,
    )
    ranked = [record for record in scored if _lookalike_score(record, profile) > 0][: max(1, top_k)]
    warnings = [f"K2 not configured; ranked {len(candidates)} persisted lead(s) against {len(seed_records)} seed(s) in-memory."]
    return {
        "provider": "local",
        "corpus": corpus_key,
        "results": ranked,
        "facets": build_facets(ranked),
        "warnings": warnings,
    }


def mining_to_csv(payload: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=MINING_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for result in payload.get("results", []):
        if isinstance(result, dict):
            writer.writerow({field: result.get(field, "") for field in MINING_CSV_FIELDS})
    return buffer.getvalue()


def _load_lead_records(store: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for summary in store.list_runs():
        run_id = str(summary.get("id") or "")
        if not run_id:
            continue
        run = store.load_run(run_id)
        if not isinstance(run, dict):
            continue
        for lead in run.get("leads", []):
            if not isinstance(lead, dict):
                continue
            record = _lead_record(run, lead)
            key = f"{record['domain']}:{record['run_id']}"
            if record["domain"] and key not in seen:
                seen.add(key)
                records.append(record)
    return records


def _lead_record(run: dict[str, Any], lead: dict[str, Any]) -> dict[str, Any]:
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    classification = score.get("classification", {}) if isinstance(score.get("classification"), dict) else {}
    metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
    workflow = lead.get("workflow", {}) if isinstance(lead.get("workflow"), dict) else {}
    return shape_record(
        {
            "company": company.get("company"),
            "domain": company.get("domain"),
            "vertical": metadata.get("vertical") or company.get("vertical") or "",
            "tier": score.get("tier"),
            "ai_posture": classification.get("ai_posture"),
            "total_score": score.get("total_score"),
            "outreach_status": workflow.get("status"),
            "run_id": run.get("id"),
        },
        snippet=_lead_snippet(lead),
        citations=[str(item.get("url") or "") for item in lead.get("evidence", []) if isinstance(item, dict)],
    )


def _lead_snippet(lead: dict[str, Any]) -> str:
    strategy = lead.get("strategy", {}) if isinstance(lead.get("strategy"), dict) else {}
    if strategy.get("outreach_angle"):
        return str(strategy.get("outreach_angle"))
    for item in lead.get("evidence", []):
        if isinstance(item, dict) and item.get("text"):
            return str(item.get("text"))
    return ""


def _matches_clauses(record: dict[str, Any], clauses: list[tuple[str, str, Any]]) -> bool:
    for key, op, value in clauses:
        if key not in _LOCAL_FIELDS:
            continue  # not evaluable offline; surfaced as a warning, not a silent exclude
        if not _match_clause(record.get(key), op, value):
            return False
    return True


def _match_clause(field: Any, op: str, value: Any) -> bool:
    if op in {">", ">=", "<", "<=", "==", "!="} and _is_number(value) and _is_number(field):
        left, right = float(field), float(value)
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        return left <= right
    if op in {">", ">=", "<", "<="}:
        # A non-numeric operand can't be ordered; don't silently fall through to
        # the string-equality return below (a `<` clause behaving like `==`).
        return False
    if op == "in":
        values = {str(item).strip().lower() for item in value} if isinstance(value, (list, tuple, set)) else {str(value).strip().lower()}
        return str(field or "").strip().lower() in values
    if op == "contains":
        return str(value).strip().lower() in str(field or "").strip().lower()
    if op == "!=":
        return str(field or "").strip().lower() != str(value or "").strip().lower()
    return str(field or "").strip().lower() == str(value or "").strip().lower()


def _rank_by_query(records: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    tokens = [token for token in str(query or "").lower().split() if len(token) > 2]
    if not tokens:
        return sorted(records, key=lambda record: _score_value(record.get("total_score")), reverse=True)

    def relevance(record: dict[str, Any]) -> int:
        haystack = " ".join(
            str(record.get(field) or "") for field in ("company", "domain", "vertical", "ai_posture", "snippet")
        ).lower()
        return sum(1 for token in tokens if token in haystack)

    scored = [(relevance(record), record) for record in records]
    return [record for _, record in sorted(scored, key=lambda pair: (pair[0], _score_value(pair[1].get("total_score"))), reverse=True)]


def _seed_profile(seed_records: list[dict[str, Any]]) -> dict[str, Any]:
    verticals = {record["vertical"].lower() for record in seed_records if record.get("vertical")}
    postures = {record["ai_posture"].lower() for record in seed_records if record.get("ai_posture")}
    tiers = {record["tier"].upper() for record in seed_records if record.get("tier")}
    scores = [_score_value(record.get("total_score")) for record in seed_records if _is_number(record.get("total_score"))]
    return {
        "verticals": verticals,
        "postures": postures,
        "tiers": tiers,
        "avg_score": sum(scores) / len(scores) if scores else 0.0,
    }


def _lookalike_score(record: dict[str, Any], profile: dict[str, Any]) -> int:
    score = 0
    if record.get("vertical") and record["vertical"].lower() in profile["verticals"]:
        score += 3
    if record.get("ai_posture") and record["ai_posture"].lower() in profile["postures"]:
        score += 2
    if record.get("tier") and record["tier"].upper() in profile["tiers"]:
        score += 1
    if profile["avg_score"] and _is_number(record.get("total_score")):
        if abs(_score_value(record.get("total_score")) - profile["avg_score"]) <= 10:
            score += 1
    return score


def _search_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    responses = payload.get("responses")
    if isinstance(responses, list) and responses and isinstance(responses[0], dict):
        results = responses[0].get("results")
        return [item for item in (results or []) if isinstance(item, dict)]
    results = payload.get("results")
    return [item for item in (results or []) if isinstance(item, dict)] if isinstance(results, list) else []


def _result_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """Flatten a K2 search hit's metadata containers into one dict.

    Live K2 hits carry their business fields (``company``/``domain``/``tier``/…) under
    ``custom_metadata`` and provenance (``source_uri``/``document_id``) under
    ``system_metadata``; older/local shapes use a plain ``metadata`` block, sometimes
    nested under ``document``/``chunk``. Merge every variant so the shaper sees the real
    fields regardless of provider shape — reading only ``metadata`` blanks every live hit.
    """
    merged: dict[str, Any] = {}
    for container in (item, item.get("document"), item.get("chunk")):
        if not isinstance(container, dict):
            continue
        for key in ("metadata", "customMetadata", "custom_metadata", "systemMetadata", "system_metadata"):
            value = container.get(key)
            if isinstance(value, dict):
                merged.update(value)
    return merged


def _result_snippet(item: dict[str, Any]) -> str:
    document = item.get("document") if isinstance(item.get("document"), dict) else {}
    chunk = item.get("chunk") if isinstance(item.get("chunk"), dict) else {}
    return str(item.get("text") or document.get("text") or chunk.get("text") or "")


def _result_citations(item: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    document = item.get("document") if isinstance(item.get("document"), dict) else {}
    candidates = [
        metadata.get("source_url"),
        metadata.get("source_uri"),
        document.get("source_uri"),
        document.get("sourceUri"),
        item.get("source_uri"),
    ]
    return [str(value) for value in candidates if value]


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _score_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
