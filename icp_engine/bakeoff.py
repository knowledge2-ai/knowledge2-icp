"""K2-vs-local empirical bake-off harness (measure before deciding).

The corpus K2 ingests is ~3,326 tiny structured documents (100–600 chars each),
not long-form text. Before deciding whether K2 earns its keep on this data shape,
we *measure*: run an identical query set through the K2 retrieval path and the
local fallback, score each of the three surfaces deterministically, and emit a
report that drives the keep / right-size / feed-rich-docs call with numbers.

Three surfaces, all with a working local fallback (K2 is fully optional):

1. Filtering/mining  — ``K2Backend.mine_corpus`` vs ``mine_local``. Scored as
   precision/recall/F1 against the *exact* match set, computed by replaying
   ``mining._matches_clauses`` over the persisted leads. Also reports the local
   miner's filter-key coverage gap (only 7 of the 48 §14.3 keys are evaluable
   offline) and its ``top_k`` truncation behavior.
2. Lookalikes        — ``K2Backend.find_lookalikes`` vs ``lookalikes_local``.
   Scored as precision@k / recall@k / MAP@k against an *independent* similarity
   label the local heuristic does not optimize: the account ``category`` (94
   operating-group-style buckets), distinct from the coarse derived ``vertical``.
3. RAG grounding     — ``K2Backend.answer_question`` vs
   ``ResearchPipeline.answer_question``. Scored as a faithfulness proxy: the
   fraction of the account's known textual facts (company, domain, tier, top
   signal) surfaced in the answer, minus tier contradictions.

The deterministic metrics need no LLM judge and no API keys. When ``K2Backend``
is unconfigured the harness still runs the local half and labels the K2 columns
"not configured", so the harness proves out end-to-end without any secret. The
live-K2 half runs the same command once a dev corpus is populated and the K2
corpus IDs + ``K2_API_KEY`` are exported.

Run offline:  ``python -m icp_engine.bakeoff``
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from .enrichment import normalize_domain
from .k2_backend import K2Backend
from .mining import (
    _LOCAL_FIELDS,
    _load_lead_records,
    _matches_clauses,
    lookalikes_local,
    mine_local,
    normalize_clauses,
)
from .seed_defaults import SEED_RUN_ID, seeded_run

# Filtering is measured at a generous top_k so precision/recall reflect filter
# *correctness*, not the product default's truncation. The default (20) is
# reported separately as a UX note (large WHERE-clause result sets get cut).
_FILTER_TOP_K = 500
_LOOKALIKE_K = 10
_GROUNDING_SAMPLE_PER_TIER = 2

_TIER_CLAIM = re.compile(r"tier\s+([a-d]|reject)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Query set (fixtures — no new data files)
# ---------------------------------------------------------------------------


def filtering_queries() -> list[dict[str, Any]]:
    """Filtering cases: the seeded query profiles + adversarial filters.

    The seeded profiles are taken verbatim so we measure the angles the product
    actually ships. The adversarial set stresses the local 7/48-key gap, numeric
    ranges, multi-clause ``and``, and ``in``/``contains`` operators.
    """
    from .seed_defaults import SEEDED_QUERY_PROFILES

    cases: list[dict[str, Any]] = []
    for profile in SEEDED_QUERY_PROFILES:
        queries = profile.get("queries") or [""]
        cases.append(
            {
                "id": f"profile:{profile.get('id')}",
                "source": "seeded_profile",
                "query": str(queries[0]),
                "filters": profile.get("filters") or [],
            }
        )
    cases.extend(
        [
            {
                "id": "adv:tier-a-high-score",
                "source": "adversarial",
                "query": "",
                "filters": [
                    {"key": "tier", "op": "==", "value": "A"},
                    {"key": "total_score", "op": ">=", "value": 80},
                ],
            },
            {
                "id": "adv:ab-tier-midscore",
                "source": "adversarial",
                "query": "",
                "filters": [
                    {"key": "tier", "op": "in", "value": ["A", "B"]},
                    {"key": "total_score", "op": ">=", "value": 70},
                ],
            },
            {
                "id": "adv:posture-level-1",
                "source": "adversarial",
                "query": "",
                "filters": [{"key": "ai_posture", "op": "==", "value": "1"}],
            },
            {
                "id": "adv:company-contains",
                "source": "adversarial",
                "query": "",
                "filters": [{"key": "company", "op": "contains", "value": "service"}],
            },
            {
                "id": "adv:unevaluable-contact-path",
                "source": "adversarial",
                "query": "",
                # has_contact_path is a valid §14.3 key the local miner can't
                # evaluate — exercises the coverage-gap reporting.
                "filters": [{"key": "has_contact_path", "op": "==", "value": True}],
            },
        ]
    )
    return cases


def lookalike_seeds(category_by_domain: dict[str, str], *, count: int = 5) -> list[dict[str, Any]]:
    """Pick one seed per populated category so overlap@k has relevant peers to hit."""
    by_category: dict[str, list[str]] = {}
    for domain, category in category_by_domain.items():
        if category:
            by_category.setdefault(category, []).append(domain)
    # Deterministic: largest categories first (most peers), then domain order.
    ranked = sorted(by_category.items(), key=lambda item: (-len(item[1]), item[0]))
    seeds: list[dict[str, Any]] = []
    for category, domains in ranked:
        if len(domains) < 2:
            continue  # no peers to find — not a useful lookalike test
        seed_domain = sorted(domains)[0]
        seeds.append({"id": f"seed:{seed_domain}", "domain": seed_domain, "category": category})
        if len(seeds) >= count:
            break
    return seeds


def grounding_cases(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Sample accounts across tiers; each carries its known textual facts."""
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for lead in run.get("leads", []):
        score = lead.get("score", {})
        tier = str(score.get("tier") or "")
        by_tier.setdefault(tier, []).append(lead)
    cases: list[dict[str, Any]] = []
    for tier in sorted(by_tier):
        for lead in by_tier[tier][:_GROUNDING_SAMPLE_PER_TIER]:
            score = lead.get("score", {})
            company = score.get("company", {})
            metadata = lead.get("metadata", {}) if isinstance(lead.get("metadata"), dict) else {}
            classification = score.get("classification", {}) if isinstance(score.get("classification"), dict) else {}
            cases.append(
                {
                    "id": f"ground:{normalize_domain(str(company.get('domain') or ''))}",
                    "company": str(company.get("company") or ""),
                    "domain": normalize_domain(str(company.get("domain") or "")),
                    "tier": tier,
                    # The vertical is a real classification label the dossier surfaces
                    # in prose ("Vertical: …") but the account-summary text omits — so
                    # it discriminates dossier-grounded answers from label-dump ones,
                    # which the 4 saturating facts (company/domain/tier/signal) cannot.
                    "vertical": str(metadata.get("vertical") or classification.get("vertical") or ""),
                    "signal_tags": [str(tag) for tag in metadata.get("signal_tags", []) if str(tag).strip()],
                }
            )
    return cases


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------


def ground_truth_matches(records: list[dict[str, Any]], clauses: list[tuple[str, str, Any]]) -> set[str]:
    """Exact filter match set: replay ``_matches_clauses`` over every record.

    Unevaluable keys are skipped by ``_matches_clauses`` (surfaced as a coverage
    gap, not a silent exclude), so this is the gold the local *and* K2 paths are
    scored against on the keys that are actually evaluable offline.
    """
    return {
        normalize_domain(str(record.get("domain") or ""))
        for record in records
        if _matches_clauses(record, clauses)
    }


def category_by_domain(run: dict[str, Any]) -> dict[str, str]:
    """Independent similarity label for lookalikes: account ``category``.

    Distinct from the local heuristic's coarse derived ``vertical`` (which is
    additionally empty on the seed metadata), so it is a fair, un-gamed relevance
    label the local ranker does not optimize against.
    """
    mapping: dict[str, str] = {}
    for lead in run.get("leads", []):
        company = lead.get("score", {}).get("company", {})
        domain = normalize_domain(str(company.get("domain") or ""))
        if domain:
            mapping[domain] = str(company.get("category") or "")
    return mapping


# ---------------------------------------------------------------------------
# Scorers (pure, deterministic)
# ---------------------------------------------------------------------------


def score_filtering(result: dict[str, Any], gold: set[str], clauses: list[tuple[str, str, Any]]) -> dict[str, Any]:
    predicted = {normalize_domain(str(r.get("domain") or "")) for r in result.get("results", []) if r.get("domain")}
    tp = len(predicted & gold)
    precision = _safe_ratio(tp, len(predicted), empty_both=not gold)
    recall = _safe_ratio(tp, len(gold), empty_both=not predicted)
    f1 = _safe_ratio(2 * precision * recall, precision + recall) if (precision + recall) else (1.0 if not gold and not predicted else 0.0)
    unevaluable = sorted({key for key, _, _ in clauses if key not in _LOCAL_FIELDS})
    return {
        "predicted_count": len(predicted),
        "gold_count": len(gold),
        "true_positives": tp,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "unevaluable_keys": unevaluable,
    }


def score_lookalikes(result: dict[str, Any], seed_domain: str, category_label: dict[str, str], k: int) -> dict[str, Any]:
    seed_category = category_label.get(seed_domain, "")
    relevant = {
        domain
        for domain, category in category_label.items()
        if category and category == seed_category and domain != seed_domain
    }
    predicted = [normalize_domain(str(r.get("domain") or "")) for r in result.get("results", []) if r.get("domain")][:k]
    hits = [domain for domain in predicted if domain in relevant]
    precision_at_k = _safe_ratio(len(hits), len(predicted), empty_both=not relevant)
    recall_at_k = _safe_ratio(len(set(hits)), len(relevant), empty_both=not predicted)
    return {
        "seed_category": seed_category,
        "relevant_count": len(relevant),
        "predicted_count": len(predicted),
        "hits": len(hits),
        "precision_at_k": round(precision_at_k, 4),
        "recall_at_k": round(recall_at_k, 4),
        "map_at_k": round(_average_precision(predicted, relevant), 4),
    }


def score_grounding(answer: str, case: dict[str, Any]) -> dict[str, Any]:
    text = str(answer or "").lower()
    facts: list[tuple[str, bool]] = []
    if case.get("company"):
        facts.append(("company", str(case["company"]).lower() in text))
    if case.get("domain"):
        facts.append(("domain", str(case["domain"]).lower() in text))
    if case.get("tier"):
        facts.append(("tier", f"tier {str(case['tier']).lower()}" in text))
    if case.get("vertical"):
        facts.append(("vertical", str(case["vertical"]).lower() in text))
    for tag in case.get("signal_tags", [])[:3]:
        facts.append((f"signal:{tag}", str(tag).lower() in text))
    surfaced = sum(1 for _, present in facts if present)
    coverage = _safe_ratio(surfaced, len(facts), empty_both=False) if facts else 0.0
    contradiction = _tier_contradiction(text, str(case.get("tier") or ""))
    grounding = max(0.0, coverage - (1.0 if contradiction else 0.0))
    return {
        "facts_checked": len(facts),
        "facts_surfaced": surfaced,
        "coverage": round(coverage, 4),
        "tier_contradiction": contradiction,
        "grounding_score": round(grounding, 4),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_bakeoff(store: Any, *, k2: K2Backend | None = None, run_id: str = SEED_RUN_ID) -> dict[str, Any]:
    """Run all three surfaces over the query set; time each call; return a report dict."""
    k2 = k2 if k2 is not None else K2Backend(k2_settings=store.tenant_config.k2)
    k2_on = bool(k2.configured)
    run = store.load_run(run_id) or seeded_run()
    records = _load_lead_records(store)
    category_label = category_by_domain(run)

    report: dict[str, Any] = {
        "run_id": run_id,
        "record_count": len(records),
        "k2_configured": k2_on,
        "config": {
            "filter_top_k": _FILTER_TOP_K,
            "lookalike_k": _LOOKALIKE_K,
            "grounding_sample_per_tier": _GROUNDING_SAMPLE_PER_TIER,
            "local_evaluable_keys": sorted(_LOCAL_FIELDS),
        },
        "filtering": _run_filtering(store, k2, records, k2_on),
        "lookalikes": _run_lookalikes(store, k2, category_label, k2_on),
        "grounding": _run_grounding(store, k2, run, run_id, k2_on),
    }
    report["summary"] = _summarize(report)
    return report


def _run_filtering(store: Any, k2: K2Backend, records: list[dict[str, Any]], k2_on: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in filtering_queries():
        clauses = normalize_clauses(case["filters"])
        gold = ground_truth_matches(records, clauses)
        local_result, local_ms = _timed(
            lambda: mine_local(store, query=case["query"], clauses=clauses, top_k=_FILTER_TOP_K)
        )
        row: dict[str, Any] = {
            "case_id": case["id"],
            "source": case["source"],
            "query": case["query"],
            "filters": case["filters"],
            "gold_count": len(gold),
            "local": {**score_filtering(local_result, gold, clauses), "latency_ms": local_ms},
        }
        if k2_on:
            k2_result, k2_ms = _timed(
                lambda: k2.mine_corpus(
                    query=case["query"], filters=case["filters"], top_k=_FILTER_TOP_K, store=store
                )
            )
            row["k2"] = {**score_filtering(k2_result, gold, clauses), "latency_ms": k2_ms, "provider": k2_result.get("provider")}
        rows.append(row)
    return rows


def _run_lookalikes(store: Any, k2: K2Backend, category_label: dict[str, str], k2_on: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed in lookalike_seeds(category_label):
        domain = seed["domain"]
        local_result, local_ms = _timed(
            lambda: lookalikes_local(store, seed_domains=[domain], top_k=_LOOKALIKE_K)
        )
        row: dict[str, Any] = {
            "seed_id": seed["id"],
            "seed_domain": domain,
            "seed_category": seed["category"],
            "local": {**score_lookalikes(local_result, domain, category_label, _LOOKALIKE_K), "latency_ms": local_ms},
        }
        if k2_on:
            k2_result, k2_ms = _timed(
                lambda: k2.find_lookalikes(seed_domains=[domain], top_k=_LOOKALIKE_K, store=store)
            )
            row["k2"] = {**score_lookalikes(k2_result, domain, category_label, _LOOKALIKE_K), "latency_ms": k2_ms, "provider": k2_result.get("provider")}
        rows.append(row)
    return rows


def _run_grounding(store: Any, k2: K2Backend, run: dict[str, Any], run_id: str, k2_on: bool) -> list[dict[str, Any]]:
    from .research import ResearchPipeline

    pipeline = ResearchPipeline(store, k2_backend=k2)
    rows: list[dict[str, Any]] = []
    for case in grounding_cases(run):
        question = (
            f"What do we already know about {case['company']} ({case['domain']})? "
            "Summarize their tier, AI posture, and any buying signals."
        )
        local_answer, local_ms = _timed(
            lambda: pipeline.answer_question(run_id=run_id, question=question)
        )
        row: dict[str, Any] = {
            "case_id": case["id"],
            "company": case["company"],
            "domain": case["domain"],
            "tier": case["tier"],
            "local": {**score_grounding(str(local_answer.get("answer") or ""), case), "latency_ms": local_ms, "provider": local_answer.get("provider")},
        }
        if k2_on:
            k2_answer, k2_ms = _timed(lambda: k2.answer_question(run, question))
            row["k2"] = {**score_grounding(str(k2_answer.get("answer") or ""), case), "latency_ms": k2_ms, "provider": k2_answer.get("provider"), "status": k2_answer.get("status")}
        rows.append(row)
    return rows


def _summarize(report: dict[str, Any]) -> dict[str, Any]:
    filtering = report["filtering"]
    lookalikes = report["lookalikes"]
    grounding = report["grounding"]
    summary = {
        "filtering": {
            "local_mean_f1": _mean([row["local"]["f1"] for row in filtering]),
            "local_mean_latency_ms": _mean([row["local"]["latency_ms"] for row in filtering]),
            "cases_with_coverage_gap": sum(1 for row in filtering if row["local"]["unevaluable_keys"]),
            "case_count": len(filtering),
        },
        "lookalikes": {
            "local_mean_precision_at_k": _mean([row["local"]["precision_at_k"] for row in lookalikes]),
            "local_mean_map_at_k": _mean([row["local"]["map_at_k"] for row in lookalikes]),
            "local_mean_latency_ms": _mean([row["local"]["latency_ms"] for row in lookalikes]),
            "case_count": len(lookalikes),
        },
        "grounding": {
            "local_mean_grounding": _mean([row["local"]["grounding_score"] for row in grounding]),
            "local_mean_coverage": _mean([row["local"]["coverage"] for row in grounding]),
            "local_mean_latency_ms": _mean([row["local"]["latency_ms"] for row in grounding]),
            "case_count": len(grounding),
        },
    }
    if report["k2_configured"]:
        summary["filtering"]["k2_mean_f1"] = _mean([row["k2"]["f1"] for row in filtering if "k2" in row])
        summary["lookalikes"]["k2_mean_precision_at_k"] = _mean([row["k2"]["precision_at_k"] for row in lookalikes if "k2" in row])
        summary["grounding"]["k2_mean_grounding"] = _mean([row["k2"]["grounding_score"] for row in grounding if "k2" in row])
    return summary


# ---------------------------------------------------------------------------
# Output (CSV + Markdown)
# ---------------------------------------------------------------------------

BAKEOFF_CSV_FIELDS = ["dimension", "case_id", "path", "metric", "value"]


def bakeoff_to_csv(report: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=BAKEOFF_CSV_FIELDS)
    writer.writeheader()
    paths = ["local", "k2"] if report["k2_configured"] else ["local"]
    for row in report["filtering"]:
        for path in paths:
            for metric in ("precision", "recall", "f1", "predicted_count", "gold_count", "latency_ms"):
                if path in row and metric in row[path]:
                    writer.writerow({"dimension": "filtering", "case_id": row["case_id"], "path": path, "metric": metric, "value": row[path][metric]})
    for row in report["lookalikes"]:
        for path in paths:
            for metric in ("precision_at_k", "recall_at_k", "map_at_k", "relevant_count", "latency_ms"):
                if path in row and metric in row[path]:
                    writer.writerow({"dimension": "lookalikes", "case_id": row["seed_id"], "path": path, "metric": metric, "value": row[path][metric]})
    for row in report["grounding"]:
        for path in paths:
            for metric in ("coverage", "grounding_score", "facts_surfaced", "facts_checked", "latency_ms"):
                if path in row and metric in row[path]:
                    writer.writerow({"dimension": "grounding", "case_id": row["case_id"], "path": path, "metric": metric, "value": row[path][metric]})
    return output.getvalue()


def bakeoff_to_markdown(report: dict[str, Any]) -> str:
    k2_on = report["k2_configured"]
    k2_note = "K2 columns are live." if k2_on else "**K2 not configured** — K2 columns read `n/a`; only the local half is measured."
    lines = [
        "# K2 vs local bake-off",
        "",
        f"- Run: `{report['run_id']}` · {report['record_count']} persisted lead records",
        f"- {k2_note}",
        f"- Filtering measured at top_k={report['config']['filter_top_k']} (correctness); product default is 20 (truncates large result sets).",
        f"- Local miner evaluates {len(report['config']['local_evaluable_keys'])} of 48 §14.3 filter keys offline: "
        + ", ".join(f"`{key}`" for key in report["config"]["local_evaluable_keys"])
        + ".",
        "",
        "## Filtering (precision/recall/F1 vs exact match set)",
        "",
    ]
    header = "| Case | Source | Gold | Local P | Local R | Local F1 | Local ms | Coverage gap |"
    sep = "|---|---|---:|---:|---:|---:|---:|---|"
    if k2_on:
        header = "| Case | Source | Gold | Local F1 | K2 F1 | Local ms | K2 ms | Coverage gap |"
    lines += [header, sep]
    for row in report["filtering"]:
        gap = ", ".join(f"`{key}`" for key in row["local"]["unevaluable_keys"]) or "—"
        if k2_on:
            lines.append(
                f"| {row['case_id']} | {row['source']} | {row['gold_count']} | {row['local']['f1']} | "
                f"{row['k2']['f1']} | {row['local']['latency_ms']} | {row['k2']['latency_ms']} | {gap} |"
            )
        else:
            lo = row["local"]
            lines.append(
                f"| {row['case_id']} | {row['source']} | {row['gold_count']} | {lo['precision']} | "
                f"{lo['recall']} | {lo['f1']} | {lo['latency_ms']} | {gap} |"
            )
    lines += ["", "## Lookalikes (precision@k / MAP@k vs independent `category` label)", ""]
    if k2_on:
        lines += ["| Seed | Category | Peers | Local P@k | K2 P@k | Local MAP | K2 MAP |", "|---|---|---:|---:|---:|---:|---:|"]
        for row in report["lookalikes"]:
            lines.append(
                f"| {row['seed_domain']} | {row['seed_category']} | {row['local']['relevant_count']} | "
                f"{row['local']['precision_at_k']} | {row['k2']['precision_at_k']} | {row['local']['map_at_k']} | {row['k2']['map_at_k']} |"
            )
    else:
        lines += ["| Seed | Category | Peers | Local P@k | Local R@k | Local MAP | Local ms |", "|---|---|---:|---:|---:|---:|---:|"]
        for row in report["lookalikes"]:
            lo = row["local"]
            lines.append(
                f"| {row['seed_domain']} | {row['seed_category']} | {lo['relevant_count']} | "
                f"{lo['precision_at_k']} | {lo['recall_at_k']} | {lo['map_at_k']} | {lo['latency_ms']} |"
            )
    lines += ["", "## Grounding (known-fact coverage − contradictions)", ""]
    if k2_on:
        lines += ["| Account | Tier | Local cov | K2 cov | Local score | K2 score |", "|---|---|---:|---:|---:|---:|"]
        for row in report["grounding"]:
            lines.append(
                f"| {row['domain']} | {row['tier']} | {row['local']['coverage']} | {row['k2']['coverage']} | "
                f"{row['local']['grounding_score']} | {row['k2']['grounding_score']} |"
            )
    else:
        lines += ["| Account | Tier | Facts | Local coverage | Local score | Local ms |", "|---|---|---:|---:|---:|---:|"]
        for row in report["grounding"]:
            lo = row["local"]
            lines.append(
                f"| {row['domain']} | {row['tier']} | {lo['facts_surfaced']}/{lo['facts_checked']} | "
                f"{lo['coverage']} | {lo['grounding_score']} | {lo['latency_ms']} |"
            )
    summary = report["summary"]
    lines += [
        "",
        "## Summary",
        "",
        f"- Filtering: local mean F1 **{summary['filtering']['local_mean_f1']}** over {summary['filtering']['case_count']} cases; "
        f"{summary['filtering']['cases_with_coverage_gap']} case(s) hit the offline key-coverage gap.",
        f"- Lookalikes: local mean precision@k **{summary['lookalikes']['local_mean_precision_at_k']}**, MAP@k {summary['lookalikes']['local_mean_map_at_k']}.",
        f"- Grounding: local mean coverage **{summary['grounding']['local_mean_coverage']}**, grounding score {summary['grounding']['local_mean_grounding']}.",
    ]
    if not k2_on:
        lines += [
            "",
            "_To populate the K2 columns: `python -m icp_engine.k2_sync --apply` to provision + upload the "
            "corpus, export the returned `K2_*_CORPUS_ID` values + `K2_API_KEY`, then re-run this command._",
        ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _timed(thunk) -> tuple[Any, float]:
    start = time.perf_counter()
    value = thunk()
    return value, round((time.perf_counter() - start) * 1000, 3)


def _safe_ratio(numerator: float, denominator: float, *, empty_both: bool = False) -> float:
    if denominator <= 0:
        return 1.0 if empty_both else 0.0
    return numerator / denominator


def _average_precision(predicted: list[str], relevant: set[str]) -> float:
    if not relevant:
        return 1.0 if not predicted else 0.0
    hits = 0
    summed = 0.0
    for index, domain in enumerate(predicted, start=1):
        if domain in relevant:
            hits += 1
            summed += hits / index
    return summed / min(len(relevant), len(predicted)) if predicted else 0.0


def _tier_contradiction(text: str, known_tier: str) -> bool:
    if not known_tier:
        return False
    claimed = {match.group(1).lower() for match in _TIER_CLAIM.finditer(text)}
    if not claimed:
        return False
    return known_tier.lower() not in claimed


def _mean(values: list[float]) -> float:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return round(sum(numeric) / len(numeric), 4) if numeric else 0.0


def _build_offline_store() -> Any:
    """A default-tenant store with no persisted runs serves the 428-account seed run."""
    from .app_store import AppStore

    tmp = Path(tempfile.mkdtemp(prefix="bakeoff-"))
    return AppStore(tmp / "state", tmp / "missing-icp.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K2 vs local retrieval bake-off (deterministic).")
    parser.add_argument("--run", default=SEED_RUN_ID, help="Run id to measure (default: seeded run).")
    parser.add_argument("--out", default="bakeoff-report.md", help="Markdown report path.")
    parser.add_argument("--csv", default="bakeoff.csv", help="CSV path.")
    args = parser.parse_args(argv)

    store = _build_offline_store()
    report = run_bakeoff(store, run_id=args.run)

    Path(args.out).write_text(bakeoff_to_markdown(report), encoding="utf-8")
    Path(args.csv).write_text(bakeoff_to_csv(report), encoding="utf-8")

    summary = report["summary"]
    state = "live" if report["k2_configured"] else "not configured"
    print(f"Bake-off complete ({report['record_count']} records; K2 {state}).")
    print(f"  Filtering   local mean F1: {summary['filtering']['local_mean_f1']}  ({summary['filtering']['cases_with_coverage_gap']} coverage-gap case(s))")
    print(f"  Lookalikes  local mean P@k: {summary['lookalikes']['local_mean_precision_at_k']}  MAP@k: {summary['lookalikes']['local_mean_map_at_k']}")
    print(f"  Grounding   local mean coverage: {summary['grounding']['local_mean_coverage']}  score: {summary['grounding']['local_mean_grounding']}")
    print(f"  Wrote {args.out} and {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
