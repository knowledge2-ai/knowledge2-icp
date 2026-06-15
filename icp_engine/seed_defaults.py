from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import strategy as strategy_module
from .models import (
    Classification,
    CompanyInput,
    Evidence,
    GateResult,
    GateStatus,
    ScoreResult,
)
from .scoring import _ai_gap_points
from .serialization import score_to_dict


# Plain data directory holding the knowledge2 tenant's externalized seed data
# (mirrors the non-package ``web_assets`` data-dir convention — no ``__init__.py``).
_KNOWLEDGE2_DIR = Path(__file__).with_name("tenants") / "knowledge2"


SEEDED_CRITERIA_MARKDOWN = (_KNOWLEDGE2_DIR / "criteria.md").read_text(encoding="utf-8")


SEEDED_PROMPTS: list[dict[str, Any]] = json.loads(
    (_KNOWLEDGE2_DIR / "prompts.json").read_text(encoding="utf-8")
)


SEEDED_SETTINGS: dict[str, Any] = json.loads(
    (_KNOWLEDGE2_DIR / "settings.json").read_text(encoding="utf-8")
)


# Named query profiles (PRD §14.4) seeded so corpus mining starts with the standard
# ICP search angles. Each profile pairs example queries with metadata-filter hints over
# the §14.3 keys; profiles drive `mine_corpus` so the named angles are operable, not just
# topology metadata.
SEEDED_QUERY_PROFILES: list[dict[str, Any]] = json.loads(
    (_KNOWLEDGE2_DIR / "query_profiles.json").read_text(encoding="utf-8")
)


def _load_seed_accounts() -> list[dict[str, Any]]:
    path = Path(__file__).with_name("web_assets") / "seed-companies.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("account_universe", [])


# account_universe stays sourced from web_assets/seed-companies.json (bundled into the
# Cloudflare worker); priority_verticals is externalized to tenants/knowledge2/lists.json.
SEEDED_LISTS: dict[str, Any] = {
    "account_universe": _load_seed_accounts(),
    **json.loads((_KNOWLEDGE2_DIR / "lists.json").read_text(encoding="utf-8")),
}


SEED_RUN_ID = "run-seeded-icp"
SEED_CREATED_AT = "2026-06-12T00:00:00+00:00"


def seeded_run() -> dict[str, Any]:
    run = {
        "id": SEED_RUN_ID,
        "query": SEEDED_SETTINGS["default_query"],
        "created_at": SEED_CREATED_AT,
        "status": "completed",
        # Mirror the live run shape from research.ResearchPipeline.run: rule-scored
        # fixtures expose qualifier "rules" and a seeded discovery provider.
        "qualifier": "rules",
        "discovery": {"provider": "seeded"},
        "criteria": {
            "hash": "seeded-icp-v1",
            "source": "icp.md",
            "updated_at": SEED_CREATED_AT,
            "profile": {
                "source": "icp.md",
                "hash": "seeded-icp-v1",
                "tier_a_threshold": 75,
                "tier_b_threshold": 60,
                "min_employee_count": 25,
                "max_employee_count": 2000,
                "priority_terms": list(SEEDED_LISTS["priority_verticals"]),
                "warnings": [],
            },
        },
        "warnings": [],
        "leads": sorted(
            [_seed_lead_from_account(account) for account in SEEDED_LISTS["account_universe"]],
            key=lambda lead: (-int(lead["score"]["total_score"]), str(lead["score"]["company"]["company"])),
        ),
    }
    run["k2"] = {
        "status": "ready_for_sdk_sync",
        "reason": "Seeded Worker/Python deployment can export this manifest to K2 when K2_API_KEY is configured.",
        "document_count": len(run["leads"]) * 6,
    }
    return deepcopy(run)


def _seed_lead_from_account(account: dict[str, Any]) -> dict[str, Any]:
    qualification = _qualification_for(account)
    vertical = _vertical_for(account)
    # ``reject`` is an intrinsic signal (AI-native positioning), not a tier readout:
    # tier itself is derived from the computed score + gates below, so it must never
    # feed back into level/score derivation.
    reject = "ai-native" in f"{account.get('category', '')} {account.get('notes', '')}".lower()
    high_priority = _high_priority_vertical(vertical)

    # Classification LEVELS (0-5) come from intrinsic seed signals only. Where a
    # qualification dict carries explicit component scores, recover the matching level
    # so the displayed classification stays consistent with the honored override scores.
    ai_posture = _qualified_int(qualification, "ai_posture", 5 if reject else 1)
    data_workflow = _component_level(qualification, "data_workflow_score", 1 if reject else (5 if high_priority else 4))
    commercial_urgency = 1 if reject else 3
    budget_access = 1 if reject else 3
    feasibility = _component_level(qualification, "feasibility_score", 2 if reject else 3)

    # Component SCORES use the exact live formulas from scoring.score_company. If the
    # account carries explicit override scores, honor them and recompute the total as
    # their sum so the (total == sum of components) invariant always holds.
    ai_gap_score = _qualified_int(qualification, "ai_gap_score", _ai_gap_points(ai_posture))
    data_workflow_score = _qualified_int(qualification, "data_workflow_score", round((data_workflow / 5) * 25))
    commercial_urgency_score = _qualified_int(qualification, "commercial_urgency_score", round((commercial_urgency / 5) * 20))
    budget_access_score = _qualified_int(qualification, "budget_access_score", round((budget_access / 5) * 15))
    feasibility_score = _qualified_int(qualification, "feasibility_score", round((feasibility / 5) * 10))
    total_score = ai_gap_score + data_workflow_score + commercial_urgency_score + budget_access_score + feasibility_score

    return _seed_lead(
        company=str(account.get("company", "")),
        domain=str(account.get("domain", "")),
        category=str(account.get("category", "")),
        founded_year=account.get("founded_year"),
        employee_count=account.get("employee_count"),
        hq=str(account.get("hq", "")),
        reject=reject,
        ai_posture=ai_posture,
        data_workflow=data_workflow,
        commercial_urgency=commercial_urgency,
        budget_access=budget_access,
        feasibility=feasibility,
        ai_gap_score=ai_gap_score,
        data_workflow_score=data_workflow_score,
        commercial_urgency_score=commercial_urgency_score,
        budget_access_score=budget_access_score,
        feasibility_score=feasibility_score,
        total_score=total_score,
        vertical=vertical,
        evidence_text=str(account.get("notes") or f"{account.get('company')} is listed in a seeded vertical-market software portfolio."),
        source_url=str(account.get("source_url") or f"https://{account.get('domain', '')}"),
        docs_url="",
        github_url="",
        linkedin_url="",
        qualification=qualification,
    )


def _seed_lead(
    *,
    company: str,
    domain: str,
    category: str,
    founded_year: int | None,
    employee_count: int | None,
    hq: str,
    reject: bool,
    ai_posture: int,
    data_workflow: int,
    commercial_urgency: int,
    budget_access: int,
    feasibility: int,
    ai_gap_score: int,
    data_workflow_score: int,
    commercial_urgency_score: int,
    budget_access_score: int,
    feasibility_score: int,
    total_score: int,
    vertical: str,
    evidence_text: str,
    source_url: str,
    docs_url: str,
    github_url: str,
    linkedin_url: str,
    qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    qualification = qualification or {}
    notes = next(
        (item["notes"] for item in SEEDED_LISTS["account_universe"] if item["domain"] == domain),
        "",
    )
    company_input = CompanyInput(
        company=company,
        domain=domain,
        category=category,
        founded_year=founded_year,
        employee_count=employee_count,
        hq=hq,
        notes=notes,
    )
    evidence_obj = Evidence(
        evidence_id="seed-evidence",
        url=source_url,
        title="Seeded local evidence",
        text=evidence_text,
        source_type="website",
        metadata={
            "page_category": "product",
            "links": [value for value in [docs_url, github_url, linkedin_url] if value],
            "external_links": [value for value in [github_url, linkedin_url] if value],
        },
    )

    classification_source = str(qualification.get("classification_source") or "seed")
    # The five Classification.reasons component keys mirror scoring._rules_classification
    # so seed and live leads expose the same reasons shape (plus the "criteria" key the
    # scorer appends). Built directly from intrinsic levels — never re-parsed from notes.
    classification_reasons = {
        "ai_posture": "Seeded from local ICP examples and public-positioning notes.",
        "data_workflow": f"Signals include {vertical} workflow data and operational systems.",
        "commercial_urgency": "Seeded commercial-urgency signal from the local ICP example.",
        "budget_access": "Based on seeded employee-range and public scale signals.",
        "feasibility": "Seeded feasibility signal from product and integration notes.",
        "criteria": "Scored with seeded local ICP criteria.",
    }
    classification_evidence_ids = {
        "ai_posture": ["seed-evidence"],
        "data_workflow": ["seed-evidence"],
        "commercial_urgency": ["seed-evidence"],
        "feasibility": ["seed-evidence"] if docs_url else [],
    }
    classification_confidence = (
        0.82 if qualification and not reject else 0.72 if not reject else 0.55
    )

    classification = Classification(
        ai_posture=ai_posture,
        data_workflow=data_workflow,
        commercial_urgency=commercial_urgency,
        budget_access=budget_access,
        feasibility=feasibility,
        reasons=dict(classification_reasons),
        evidence_ids=classification_evidence_ids,
        confidence=classification_confidence,
        source=classification_source,
        ai_narrative="",
    )
    gates = _gates(company_input, reject, founded_year)

    # Tier derives from score + gates exactly like scoring.score_company (seeded
    # thresholds A=75 / B=60): any failed gate forces Reject, then 75/60 split A/B/C.
    if any(gate.status == GateStatus.FAIL for gate in gates):
        tier = "Reject"
        next_action = "Reject or nurture; one or more hard gates failed."
    elif total_score >= 75:
        tier = "A"
        next_action = "Prioritize human research and outbound."
    elif total_score >= 60:
        tier = "B"
        next_action = "Review manually; qualify trigger and budget."
    else:
        tier = "C"
        next_action = "Nurture or deprioritize."

    warnings = _qualified_warnings(
        qualification,
        [f"Manual review: {gate.name} is unknown ({gate.reason})" for gate in gates if gate.status == GateStatus.UNKNOWN],
    )

    result = ScoreResult(
        company=company_input,
        gates=gates,
        classification=classification,
        ai_gap_score=ai_gap_score,
        data_workflow_score=data_workflow_score,
        commercial_urgency_score=commercial_urgency_score,
        budget_access_score=budget_access_score,
        feasibility_score=feasibility_score,
        total_score=total_score,
        tier=tier,
        next_action=next_action,
        ai_narrative="",
        warnings=warnings,
    )

    signal_tags = ["workflow", "data", "commercial"]
    if qualification:
        signal_tags.append("qualified-data")
    if docs_url:
        signal_tags.append("integration")
    is_reject = tier == "Reject"
    # metadata.qualification mirrors the live shape from research._qualification_metadata
    # (qualifier/source/confidence/ai_narrative/reasons/evidence_ids) so seed and live
    # leads expose one schema. Seed accounts are rule-scored fixtures → qualifier "rules".
    qualification_metadata = {
        "qualifier": "rules",
        "source": classification_source,
        "confidence": classification_confidence,
        "ai_narrative": "",
        "reasons": dict(classification_reasons),
        "evidence_ids": classification_evidence_ids,
    }
    source_refs = {
        "careers_urls": [],
        "contact_urls": [],
        "docs_urls": [docs_url] if docs_url else [],
        "github_urls": [github_url] if github_url else [],
        "linkedin_urls": [linkedin_url] if linkedin_url else [],
        "marketplace_urls": [],
        "other_urls": [],
        "pricing_urls": [],
        "social_urls": [],
    }

    metadata = {
        "company": company,
        "domain": domain,
        # The mining/lookalike/facet stack (mining.FACET_KEYS, _LOCAL_FIELDS,
        # _lead_record, _seed_profile) all read metadata["vertical"]; without it
        # the vertical facet renders empty, lookalikes lose their top-weighted
        # feature, and the mining CSV's vertical column is blank.
        "vertical": vertical,
        "criteria_profile": {
            "source": "icp.md",
            "hash": "seeded-icp-v1",
            "tier_a_threshold": 75,
            "tier_b_threshold": 60,
            "min_employee_count": 25,
            "max_employee_count": 2000,
            "priority_terms": list(SEEDED_LISTS["priority_verticals"]),
            "warnings": [],
        },
        "source_counts": {"website:product": 1},
        "source_refs": source_refs,
        "signal_tags": signal_tags,
        "public_profile_count": len(source_refs["github_urls"]) + len(source_refs["linkedin_urls"]),
        "public_resource_count": len(source_refs["docs_urls"]),
        "public_emails": [],
        "intelligence_coverage": {
            "has_contact_path": False,
            "has_docs_or_api": bool(docs_url),
            "has_github_profile": bool(github_url),
            "has_marketplace_profile": False,
            "has_pricing_or_commercial": not is_reject,
            "has_social_profile": bool(linkedin_url),
            "has_website_evidence": True,
        },
        "evidence_metadata": [
            {
                "evidence_id": "seed-evidence",
                "url": source_url,
                "title": "Seeded local evidence",
                "source_type": "website",
                "page_category": "product" if not is_reject else "company",
                "signal_tags": signal_tags,
                "link_count": len([value for value in [docs_url, github_url, linkedin_url] if value]),
                "external_link_count": len([value for value in [github_url, linkedin_url] if value]),
            }
        ],
        "k2_metadata_preview": {
            "company": company,
            "domain": domain,
            "signal_tags": signal_tags,
            "source_count": 1,
            "source_types": ["website:product"],
        },
        "apollo_organizations": {
            "status": "seeded",
            "reason": "Seeded account list is available before live Apollo enrichment.",
            "organizations": [],
        },
        "qualification": qualification_metadata,
    }

    return {
        "id": f"{SEED_RUN_ID}:{domain}",
        "candidate": {
            "source_url": source_url,
            "source_title": "Seeded local account list",
            "github_urls": source_refs["github_urls"],
            "linkedin_urls": source_refs["linkedin_urls"],
            "other_urls": [],
        },
        "score": score_to_dict(result),
        "strategy": strategy_module.build_strategy(result, [evidence_obj], metadata),
        "evidence": [
            {
                "evidence_id": "seed-evidence",
                "url": source_url,
                "title": "Seeded local evidence",
                "text": evidence_text,
                "source_type": "website",
                "metadata": {
                    "page_category": "product" if not is_reject else "company",
                    "links": [value for value in [docs_url, github_url, linkedin_url] if value],
                    "external_links": [value for value in [github_url, linkedin_url] if value],
                },
            }
        ],
        "metadata": metadata,
    }


def _qualification_for(account: dict[str, Any]) -> dict[str, Any]:
    value = account.get("qualification")
    return value if isinstance(value, dict) else {}


def _qualified_int(qualification: dict[str, Any], key: str, default: int) -> int:
    try:
        value = qualification.get(key)
        return int(value) if value is not None and value != "" else default
    except (TypeError, ValueError):
        return default


def _component_level(qualification: dict[str, Any], key: str, default: int) -> int:
    if key == "feasibility_score":
        return max(0, min(5, round(_qualified_int(qualification, key, default * 2) / 2)))
    return max(0, min(5, round(_qualified_int(qualification, key, default * 5) / 5)))


def _qualified_warnings(qualification: dict[str, Any], default: list[str]) -> list[str]:
    warnings = qualification.get("warnings")
    if isinstance(warnings, list):
        return [str(item) for item in warnings if str(item).strip()]
    return default


def _founded_gate(founded_year: int | None) -> GateResult:
    if founded_year:
        return GateResult("Founded before 2025", GateStatus.PASS, f"Founded year {founded_year}.")
    # Seed accounts rarely carry a founded year; the live scorer marks this gate
    # UNKNOWN (not PASS) in that case, which is what hard_gate_unknown reflects.
    return GateResult(
        "Founded before 2025",
        GateStatus.UNKNOWN,
        "Listed in official incumbent-software portfolio; founded date needs verification.",
    )


def _gates(company: CompanyInput, reject: bool, founded_year: int | None) -> list[GateResult]:
    if reject:
        return [
            _founded_gate(founded_year),
            GateResult("Product company", GateStatus.PASS, "Seeded software product."),
            GateResult("B2B or B2B2C", GateStatus.UNKNOWN, "Negative-control account."),
            GateResult("Has proprietary workflow/data", GateStatus.UNKNOWN, "No incumbent workflow data proved."),
            GateResult("Enough budget", GateStatus.UNKNOWN, "Below seeded employee range."),
            GateResult("Not AI-native", GateStatus.FAIL, "AI-native category."),
        ]
    return [
        _founded_gate(founded_year),
        GateResult("Product company", GateStatus.PASS, "Seeded software platform evidence."),
        GateResult("B2B or B2B2C", GateStatus.PASS, "Business customer and partner workflows."),
        GateResult("Has proprietary workflow/data", GateStatus.PASS, "Operational workflow and data signals."),
        GateResult("Enough budget", GateStatus.PASS, "Inside seeded employee range."),
        GateResult("Not AI-native", GateStatus.PASS, "No AI-native founding/category signal."),
    ]


def _vertical_for(account: dict[str, Any]) -> str:
    text = f"{account.get('category', '')} {account.get('notes', '')}".lower()
    if "dealer" in text or "automotive" in text:
        return "dealership"
    if "fleet" in text or "transport" in text or "telematics" in text:
        return "fleet"
    if "health" in text or "medical" in text:
        return "healthcare admin"
    if "utility" in text or "government" in text or "public" in text:
        return "govtech"
    if "asset" in text or "logistics" in text or "field" in text:
        return "field service"
    if "education" in text or "student" in text:
        return "education admin"
    if "food" in text or "hospitality" in text:
        return "hospitality"
    return str(account.get("category") or "vertical software")


def _high_priority_vertical(vertical: str) -> bool:
    text = vertical.lower()
    return any(term in text for term in ["dealer", "fleet", "field", "govtech", "health", "utility", "logistics", "manufacturing"])
