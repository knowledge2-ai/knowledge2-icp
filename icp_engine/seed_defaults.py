from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


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
    qualified_tier = str(qualification.get("tier") or "")
    reject = qualified_tier == "Reject" or "ai-native" in f"{account.get('category', '')} {account.get('notes', '')}".lower()
    vertical = _vertical_for(account)
    tier = qualified_tier if qualified_tier else ("Reject" if reject else ("A" if _high_priority_vertical(vertical) else "B"))
    fallback_score = 24 if reject else (82 if tier == "A" else 68)
    score = _qualified_int(qualification, "total_score", fallback_score)
    return _seed_lead(
        company=str(account.get("company", "")),
        domain=str(account.get("domain", "")),
        category=str(account.get("category", "")),
        founded_year=account.get("founded_year"),
        employee_count=account.get("employee_count"),
        hq=str(account.get("hq", "")),
        tier=tier,
        score=score,
        ai_posture=_qualified_int(qualification, "ai_posture", 5 if reject else 1),
        data_workflow=_component_level(qualification, "data_workflow_score", 1 if reject else (5 if tier == "A" else 4)),
        feasibility=_component_level(qualification, "feasibility_score", 2 if reject else 3),
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
    tier: str,
    score: int,
    ai_posture: int,
    data_workflow: int,
    feasibility: int,
    vertical: str,
    evidence_text: str,
    source_url: str,
    docs_url: str,
    github_url: str,
    linkedin_url: str,
    qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    qualification = qualification or {}
    signal_tags = ["workflow", "data", "commercial"]
    if qualification:
        signal_tags.append("qualified-data")
    if docs_url:
        signal_tags.append("integration")
    personas = _personas(vertical, tier)
    classification_reasons = {
        "ai_posture": "Seeded from local ICP examples and public-positioning notes.",
        "data_workflow": f"Signals include {vertical} workflow data and operational systems.",
        "criteria": "Scored with seeded local ICP criteria.",
    }
    classification_evidence_ids = {
        "ai_posture": ["seed-evidence"],
        "data_workflow": ["seed-evidence"],
        "commercial_urgency": ["seed-evidence"],
        "feasibility": ["seed-evidence"] if docs_url else [],
    }
    classification_confidence = (
        0.82 if qualification and tier != "Reject" else 0.72 if tier != "Reject" else 0.55
    )
    classification_source = str(qualification.get("classification_source") or "seed")
    # metadata.qualification mirrors the live shape from research._qualification_metadata
    # (qualifier/source/confidence/ai_narrative/reasons/evidence_ids) so seed and live
    # leads expose one schema. Seed accounts are rule-scored fixtures → qualifier "rules".
    qualification_metadata = {
        "qualifier": "rules",
        "source": classification_source,
        "confidence": classification_confidence,
        "ai_narrative": str(qualification.get("ai_narrative") or ""),
        "reasons": classification_reasons,
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
    return {
        "id": f"{SEED_RUN_ID}:{domain}",
        "candidate": {
            "source_url": source_url,
            "source_title": "Seeded local account list",
            "github_urls": source_refs["github_urls"],
            "linkedin_urls": source_refs["linkedin_urls"],
            "other_urls": [],
        },
        "score": {
            "company": {
                "company": company,
                "domain": domain,
                "category": category,
                "founded_year": founded_year,
                "employee_count": employee_count,
                "hq": hq,
                "notes": next(
                    (item["notes"] for item in SEEDED_LISTS["account_universe"] if item["domain"] == domain),
                    "",
                ),
            },
            "gates": _gates(tier, founded_year),
            "classification": {
                "ai_posture": ai_posture,
                "data_workflow": data_workflow,
                "commercial_urgency": 3 if tier != "Reject" else 1,
                "budget_access": 3 if tier != "Reject" else 1,
                "feasibility": feasibility,
                "reasons": classification_reasons,
                "evidence_ids": classification_evidence_ids,
                "confidence": classification_confidence,
                "source": classification_source,
            },
            "ai_gap_score": _qualified_int(qualification, "ai_gap_score", 30 if ai_posture <= 1 else 0),
            "data_workflow_score": _qualified_int(qualification, "data_workflow_score", min(25, data_workflow * 5)),
            "commercial_urgency_score": _qualified_int(qualification, "commercial_urgency_score", 14 if tier != "Reject" else 3),
            "budget_access_score": _qualified_int(qualification, "budget_access_score", 12 if tier != "Reject" else 2),
            "feasibility_score": _qualified_int(qualification, "feasibility_score", min(10, feasibility * 2)),
            "total_score": score,
            "tier": tier,
            "next_action": str(
                qualification.get("next_action")
                or (
                    "Prioritize for Apollo enrichment and human account research."
                    if tier == "A"
                    else "Reject from this ICP; keep only as a negative-control list item."
                )
            ),
            "warnings": _qualified_warnings(qualification, [] if tier != "Reject" else ["Fails seeded hard gates for pre-2025 non-AI-native incumbents."]),
            "hard_gate_failed": bool(qualification.get("hard_gate_failed")) if "hard_gate_failed" in qualification else tier == "Reject",
            "hard_gate_unknown": bool(qualification.get("hard_gate_unknown")) if "hard_gate_unknown" in qualification else False,
        },
        "strategy": {
            "headline": f"{company}: {_wedge(ai_posture)}",
            "wedge": _wedge(ai_posture),
            "urgency": "Peers are adding AI; durable differentiation depends on proprietary workflow data.",
            "offer": f"Propose a 2-week AI opportunity map for {vertical} workflows, grounded in existing product data and metadata.",
            "outreach_angle": (
                f"{company} appears to have meaningful {vertical} data but limited public AI positioning."
                if tier != "Reject"
                else "Not a fit: public positioning is AI-native or too early for this incumbent-software ICP."
            ),
            "first_step": "Enrich product, engineering, data, and vertical-GM contacts in Apollo.",
            "objections": ["Verify current AI roadmap ownership and commercial urgency."],
            "personas": personas,
            "apollo_titles": sorted({title for persona in personas for title in persona.get("apollo_titles", [])}),
        },
        "evidence": [
            {
                "evidence_id": "seed-evidence",
                "url": source_url,
                "title": "Seeded local evidence",
                "text": evidence_text,
                "source_type": "website",
                "metadata": {
                    "page_category": "product" if tier != "Reject" else "company",
                    "links": [value for value in [docs_url, github_url, linkedin_url] if value],
                    "external_links": [value for value in [github_url, linkedin_url] if value],
                },
            }
        ],
        "metadata": {
            "company": company,
            "domain": domain,
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
                "has_pricing_or_commercial": tier != "Reject",
                "has_social_profile": bool(linkedin_url),
                "has_website_evidence": True,
            },
            "evidence_metadata": [
                {
                    "evidence_id": "seed-evidence",
                    "url": source_url,
                    "title": "Seeded local evidence",
                    "source_type": "website",
                    "page_category": "product" if tier != "Reject" else "company",
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
        },
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


def _gates(tier: str, founded_year: int | None) -> list[dict[str, Any]]:
    if tier == "Reject":
        return [
            {"name": "Founded before 2025", "status": "fail", "reason": f"Founded year {founded_year}.", "evidence_ids": []},
            {"name": "Product company", "status": "pass", "reason": "Seeded software product.", "evidence_ids": []},
            {"name": "B2B or B2B2C", "status": "unknown", "reason": "Negative-control account.", "evidence_ids": []},
            {"name": "Has proprietary workflow/data", "status": "unknown", "reason": "No incumbent workflow data proved.", "evidence_ids": []},
            {"name": "Enough budget", "status": "fail", "reason": "Below seeded employee range.", "evidence_ids": []},
            {"name": "Not AI-native", "status": "fail", "reason": "AI-native category.", "evidence_ids": []},
        ]
    return [
        {
            "name": "Founded before 2025",
            "status": "pass" if founded_year else "unknown",
            "reason": f"Founded year {founded_year}." if founded_year else "Listed in official incumbent-software portfolio; founded date needs verification.",
            "evidence_ids": [],
        },
        {"name": "Product company", "status": "pass", "reason": "Seeded software platform evidence.", "evidence_ids": []},
        {"name": "B2B or B2B2C", "status": "pass", "reason": "Business customer and partner workflows.", "evidence_ids": []},
        {"name": "Has proprietary workflow/data", "status": "pass", "reason": "Operational workflow and data signals.", "evidence_ids": []},
        {"name": "Enough budget", "status": "pass", "reason": "Inside seeded employee range.", "evidence_ids": []},
        {"name": "Not AI-native", "status": "pass", "reason": "No AI-native founding/category signal.", "evidence_ids": []},
    ]


def _personas(vertical: str, tier: str) -> list[dict[str, Any]]:
    base = [
        {
            "title": f"VP {vertical.title()} Product" if tier != "Reject" else "Do Not Prospect",
            "priority": "primary" if tier != "Reject" else "reject",
            "rationale": "Vertical owner likely cares about workflow depth and AI differentiation.",
            "apollo_titles": [f"vp {vertical.lower()} product", "vp product", "general manager"],
        },
        {
            "title": "Chief Product Officer",
            "priority": "primary",
            "rationale": "Owns AI product strategy, roadmap tradeoffs, and customer-facing differentiation.",
            "apollo_titles": ["chief product officer", "vp product", "head of product"],
        },
        {
            "title": "VP Engineering",
            "priority": "primary",
            "rationale": "Owns integration architecture and delivery capacity for workflow AI.",
            "apollo_titles": ["vp engineering", "head of engineering", "chief technology officer"],
        },
        {
            "title": "Chief Data Officer",
            "priority": "secondary",
            "rationale": "Owns proprietary data readiness, governance, and metadata quality.",
            "apollo_titles": ["chief data officer", "head of data", "vp data"],
        },
    ]
    return base[:1] if tier == "Reject" else base


def _wedge(ai_posture: int) -> str:
    if ai_posture <= 1:
        return "turn proprietary workflow data into a visible AI product narrative"
    if ai_posture >= 4:
        return "reject or reposition toward AI governance rather than first-feature buildout"
    return "upgrade shallow AI features into governed workflow automation"


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
