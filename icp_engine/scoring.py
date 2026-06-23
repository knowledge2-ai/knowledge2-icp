from __future__ import annotations

import re
from typing import NamedTuple

from .criteria import DEFAULT_PRIORITY_TERMS, CriteriaProfile
from .models import (
    Classification,
    CompanyInput,
    Evidence,
    GateResult,
    GateStatus,
    ScoreResult,
)
from .text import keyword_counts_boundary, keyword_hits, keyword_hits_boundary, normalize_whitespace


AI_KEYWORDS = [
    "artificial intelligence",
    "generative ai",
    " genai",
    " ai ",
    "ai-powered",
    "machine learning",
    "copilot",
    "assistant",
    "chatgpt",
    "gpt",
    "llm",
    "agentic",
]

AI_NATIVE_KEYWORDS = [
    "ai-native",
    "artificial intelligence platform",
    "generative ai platform",
    "autonomous agent",
    "agents for",
    "ai agents",
    "foundation model",
]

# Category terms used almost exclusively by frontier AI labs whose founding
# premise *is* AI (the exact "Not AI-native" reject case in criteria.md), and
# essentially never by a vertical incumbent that merely bolted on a shallow AI
# feature. A single hit is enough to reject — unlike AI_NATIVE_KEYWORDS, which
# needs corroboration because "ai agents"/"agents for" also appear in passing on
# vertical-software pages. This closes the gap where Anthropic (one "ai agents"
# mention, but "ai safety"/"frontier ai" all over its site) slipped the >=2
# count while OpenAI was caught — an inconsistency on near-identical evidence.
AI_NATIVE_STRONG_KEYWORDS = [
    "frontier model",
    "frontier ai",
    "artificial general intelligence",
    "superintelligence",
    "ai safety",
    "ai research lab",
    "ai research company",
    "ai research organization",
]

THIN_AI_KEYWORDS = [
    "generate captions",
    "generate posts",
    "summarize",
    "summarization",
    "writer",
    "ask questions",
    "plain language",
    "chatbot",
    "dashboard q&a",
]

DEEP_AI_KEYWORDS = [
    "permissions",
    "governance",
    "audit",
    "human approval",
    "workflow automation",
    "trigger actions",
    "entitlement",
    "evaluation",
    "evals",
    "grounded",
    "data boundaries",
]

DATA_WORKFLOW_KEYWORDS = [
    "workflow",
    "work order",
    "dispatch",
    "claims",
    "inventory",
    "documents",
    "telematics",
    "diagnostics",
    "trips",
    "tickets",
    "inspections",
    "schedules",
    "payments",
    "transactions",
    "records",
    "portal",
    "api",
    "integrations",
    "analytics",
    "reporting",
    "compliance",
]

B2B_KEYWORDS = [
    "enterprise",
    "businesses",
    "dealership",
    "customers",
    "operators",
    "fleets",
    "teams",
    "companies",
    "partners",
    "industry",
    "platform",
]

SERVICES_KEYWORDS = [
    "consulting",
    "agency",
    "professional services",
    "managed services",
    "advisory",
]

PRODUCT_KEYWORDS = [
    "software",
    "platform",
    "saas",
    "product",
    "app",
    "suite",
    "solution",
    "cloud",
]

URGENCY_KEYWORDS = [
    "competitor",
    "automation",
    "efficiency",
    "labor",
    "cost",
    "churn",
    "retention",
    "customer experience",
    "digital transformation",
    "predictive",
    "real-time",
]

FEASIBILITY_KEYWORDS = [
    "api",
    "developer",
    "docs",
    "integration",
    "webhook",
    "cloud",
    "permissions",
    "roles",
    "sso",
    "security",
]

# Broad-audience phrasing a horizontal platform uses about itself. Presence of
# these (with no target-vertical match) caps the data/workflow moat, since the
# ICP favors focused vertical incumbents over breadth-first horizontal SaaS.
HORIZONTAL_AUDIENCE_KEYWORDS = [
    "for businesses",
    "any business",
    "all businesses",
    "businesses of all sizes",
    "any industry",
    "all industries",
    "across industries",
    "every industry",
    "any team",
    "every team",
    "any company",
    "any organization",
    "organizations of all",
    "teams of all sizes",
    "companies of all sizes",
    "millions of businesses",
    "millions of companies",
    "for everyone",
]

# The strong subset: phrases that claim an unbounded, cross-industry market.
# This is a horizontal platform's signature self-description — a focused vertical
# incumbent does not call its addressable market "businesses of all sizes" or
# "millions of businesses." Unlike the weak phrases ("for everyone", "any
# team"), these override incidental vertical mentions: Stripe names insurance
# and accounting among the industries it *serves*, which trips a naive vertical
# check, yet its own positioning is explicitly breadth-first.
HORIZONTAL_SCALE_KEYWORDS = [
    "any business",
    "all businesses",
    "businesses of all sizes",
    "any industry",
    "all industries",
    "across industries",
    "every industry",
    "organizations of all",
    "teams of all sizes",
    "companies of all sizes",
    "millions of businesses",
    "millions of companies",
]

# Fallback when a criteria profile carries no priority terms. Aliased to the
# criteria default so the two never drift — there is one canonical vertical list.
HIGH_PRIORITY_VERTICALS = DEFAULT_PRIORITY_TERMS

# Vertical *anchoring* thresholds. A vertical incumbent is anchored: its own
# category names a target vertical ("field service software"), or one vertical
# term dominates its copy. Broad/horizontal SaaS instead name-drops many
# verticals it merely *serves* (Plaid: insurance, healthcare, property, legal,
# compliance) and must not earn vertical-incumbent credit.
VERTICAL_DOMINANT_MIN = 4          # one term repeated >= this often = genuine focus...
VERTICAL_DOMINANT_MAX_DISTINCT = 2  # ...but only if <= this many distinct verticals appear
VERTICAL_SCATTER_MIN = 4           # naming >= this many distinct verticals with no anchor = horizontal tell


def score_company(
    company: CompanyInput,
    evidence: list[Evidence],
    *,
    model_classification: Classification | None = None,
    fetch_warnings: list[str] | None = None,
    criteria_profile: CriteriaProfile | None = None,
) -> ScoreResult:
    profile = criteria_profile or CriteriaProfile()
    text = _combined_text(company, evidence)
    gates = _hard_gates(company, evidence, text, profile)
    classification = _merge_classification(_rules_classification(company, evidence, text, profile), model_classification)
    classification.reasons["criteria"] = (
        f"Scored with criteria hash {profile.hash or 'default'}; "
        f"Tier A >= {profile.tier_a_threshold}, Tier B >= {profile.tier_b_threshold}, "
        f"budget range {profile.min_employee_count}-{profile.max_employee_count} employees."
    )

    ai_gap_score = _ai_gap_points(classification.ai_posture)
    data_workflow_score = round((classification.data_workflow / 5) * 25)
    commercial_urgency_score = round((classification.commercial_urgency / 5) * 20)
    budget_access_score = round((classification.budget_access / 5) * 15)
    feasibility_score = round((classification.feasibility / 5) * 10)
    total_score = ai_gap_score + data_workflow_score + commercial_urgency_score + budget_access_score + feasibility_score

    if any(gate.status == GateStatus.FAIL for gate in gates):
        tier = "Reject"
        next_action = "Reject or nurture; one or more hard gates failed."
    elif total_score >= profile.tier_a_threshold:
        tier = "A"
        next_action = "Prioritize human research and outbound."
    elif total_score >= profile.tier_b_threshold:
        tier = "B"
        next_action = "Review manually; qualify trigger and budget."
    else:
        tier = "C"
        next_action = "Nurture or deprioritize."

    # Tier A/B is reserved for vertical incumbents. A company that passed every
    # hard gate but is not anchored to a target vertical (broad/horizontal SaaS
    # that scored well on AI gap and feasibility) is deprioritized to Tier C, not
    # pursued — the ICP is "vertical software incumbents, not broad SaaS."
    if tier in {"A", "B"} and not _vertical_anchor(company, text, profile).anchored:
        tier = "C"
        next_action = "Nurture or deprioritize; no vertical anchor (broad/horizontal SaaS)."

    warnings = list(fetch_warnings or [])
    warnings.extend(_gate_warnings(gates))
    return ScoreResult(
        company=company,
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
        ai_narrative=classification.ai_narrative,
        warnings=warnings,
    )


def _combined_text(company: CompanyInput, evidence: list[Evidence]) -> str:
    chunks = [company.company, company.domain, company.category, company.hq, company.notes]
    chunks.extend(item.text for item in evidence)
    return normalize_whitespace(" ".join(chunks)).lower()


def _hard_gates(company: CompanyInput, evidence: list[Evidence], text: str, profile: CriteriaProfile) -> list[GateResult]:
    return [
        _founded_gate(company, text),
        _keyword_gate("Product company", text, PRODUCT_KEYWORDS, SERVICES_KEYWORDS),
        _keyword_gate("B2B or B2B2C", text, B2B_KEYWORDS, []),
        _keyword_gate("Has proprietary workflow/data", text, DATA_WORKFLOW_KEYWORDS, []),
        _budget_gate(company, text, profile),
        _not_ai_native_gate(text),
        _vertical_focus_gate(company, text, profile),
    ]


def _founded_gate(company: CompanyInput, text: str) -> GateResult:
    year = company.founded_year or _extract_founded_year(text)
    if year is None:
        return GateResult("Founded before 2025", GateStatus.UNKNOWN, "Founded year not found.")
    if year < 2025:
        return GateResult("Founded before 2025", GateStatus.PASS, f"Founded year {year}.")
    return GateResult("Founded before 2025", GateStatus.FAIL, f"Founded year {year} is not pre-2025.")


def _extract_founded_year(text: str) -> int | None:
    patterns = [
        r"founded in\s+(19\d{2}|20\d{2})",
        r"founded\s+(19\d{2}|20\d{2})",
        r"since\s+(19\d{2}|20\d{2})",
        r"established in\s+(19\d{2}|20\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def _keyword_gate(
    name: str,
    text: str,
    pass_keywords: list[str],
    negative_keywords: list[str],
) -> GateResult:
    positives = keyword_hits(text, pass_keywords)
    negatives = keyword_hits(text, negative_keywords)
    if positives and len(positives) >= max(1, len(negatives)):
        return GateResult(name, GateStatus.PASS, f"Found signals: {', '.join(positives[:5])}.")
    if negatives and not positives:
        return GateResult(name, GateStatus.FAIL, f"Only service-oriented signals found: {', '.join(negatives[:5])}.")
    return GateResult(name, GateStatus.UNKNOWN, "Not enough public evidence.")


def _budget_gate(company: CompanyInput, text: str, profile: CriteriaProfile) -> GateResult:
    if company.employee_count is not None:
        if profile.min_employee_count <= company.employee_count <= profile.max_employee_count:
            return GateResult(
                "Enough budget",
                GateStatus.PASS,
                f"Employee count {company.employee_count}; active criteria range {profile.min_employee_count}-{profile.max_employee_count}.",
            )
        if company.employee_count > profile.max_employee_count:
            return GateResult("Enough budget", GateStatus.PASS, f"Employee count {company.employee_count}; enterprise-size target.")
        return GateResult(
            "Enough budget",
            GateStatus.UNKNOWN,
            f"Employee count {company.employee_count}; below active criteria minimum {profile.min_employee_count} unless funded/high-ARR.",
        )
    if any(term in text for term in ["enterprise customers", "funded", "profitable", "trusted by", "thousands of customers"]):
        return GateResult("Enough budget", GateStatus.PASS, "Public copy suggests budget or customer scale.")
    return GateResult("Enough budget", GateStatus.UNKNOWN, "No employee count or funding/customer scale found.")


class VerticalAnchor(NamedTuple):
    """How a company relates to the target-vertical list: ``anchored`` (a genuine
    vertical incumbent) plus the raw signals the gate and tier-cap reason over."""

    anchored: bool
    category_hits: list[str]   # target verticals named in the company's own category
    distinct: list[str]        # distinct target verticals named anywhere in the copy
    scale_hits: list[str]      # unbounded-scale phrases ("businesses of all sizes")
    weak_hits: list[str]       # softer breadth phrases ("for any team", "for everyone")


def _vertical_anchor(company: CompanyInput, text: str, profile: CriteriaProfile) -> VerticalAnchor:
    """Decide whether a company is *anchored* to a target vertical.

    Anchored means one of two things, and crucially NOT "names a vertical
    somewhere in its copy":
    - its own CATEGORY names a target vertical ("field service software",
      "banking software") — the strongest, near-unambiguous signal; or
    - a single vertical term dominates the copy (repeated >= VERTICAL_DOMINANT_MIN
      times) while few other verticals appear — genuine focus even when the
      category string is generic.

    Broad/horizontal SaaS name-drops many verticals it merely serves (Plaid lists
    insurance, healthcare, property, legal, compliance), so scattered mentions
    must NOT confer anchoring. That is the leak this closes: previously any
    boundary-matched vertical term anywhere granted moat credit and passed the
    gate, so horizontal platforms scored Tier A/B off the industries they sell
    into."""
    terms = profile.priority_terms or HIGH_PRIORITY_VERTICALS
    category_hits = keyword_hits_boundary(company.category, terms)
    counts = keyword_counts_boundary(text, terms)
    distinct = sorted(counts)
    top_n = max(counts.values(), default=0)
    anchored = bool(category_hits) or (
        top_n >= VERTICAL_DOMINANT_MIN and len(distinct) <= VERTICAL_DOMINANT_MAX_DISTINCT
    )
    return VerticalAnchor(
        anchored=anchored,
        category_hits=category_hits,
        distinct=distinct,
        scale_hits=keyword_hits(text, HORIZONTAL_SCALE_KEYWORDS),
        weak_hits=keyword_hits(text, HORIZONTAL_AUDIENCE_KEYWORDS),
    )


def _vertical_focus_gate(company: CompanyInput, text: str, profile: CriteriaProfile) -> GateResult:
    """The ICP is "vertical software incumbents, not broad SaaS." An anchored
    company passes. A non-anchored one hard-fails only when it positively reads as
    horizontal — unbounded-scale language (Stripe: "businesses of all sizes"),
    name-dropping many unrelated verticals with no anchor (Plaid/Datadog), or
    repeated soft-breadth phrasing. A non-anchored company that is merely thin
    returns UNKNOWN (not a Reject) and is capped at Tier C downstream, so a niche
    incumbent we simply didn't enumerate is deprioritized, not thrown away."""
    name = "Vertical, not horizontal"
    anchor = _vertical_anchor(company, text, profile)
    if anchor.anchored:
        signal = anchor.category_hits or anchor.distinct
        return GateResult(name, GateStatus.PASS, f"Vertical-incumbent anchor: {', '.join(signal[:3])}.")
    if len(anchor.scale_hits) >= 2:
        return GateResult(name, GateStatus.FAIL, f"Breadth-first, cross-industry positioning: {', '.join(anchor.scale_hits[:5])}.")
    if len(anchor.distinct) >= VERTICAL_SCATTER_MIN:
        return GateResult(
            name,
            GateStatus.FAIL,
            f"Serves many unrelated verticals with no anchor (horizontal): {', '.join(anchor.distinct[:5])}.",
        )
    if len(anchor.weak_hits) >= 2:
        return GateResult(
            name,
            GateStatus.FAIL,
            f"Horizontal, breadth-first positioning with no vertical anchor: {', '.join(anchor.weak_hits[:5])}.",
        )
    return GateResult(name, GateStatus.UNKNOWN, "No vertical anchor; not clearly horizontal — capped at Tier C.")


def _not_ai_native_gate(text: str) -> GateResult:
    strong = keyword_hits(text, AI_NATIVE_STRONG_KEYWORDS)
    if strong:
        return GateResult("Not AI-native", GateStatus.FAIL, f"Frontier-AI-lab positioning: {', '.join(strong[:5])}.")
    hits = keyword_hits(text, AI_NATIVE_KEYWORDS)
    if len(hits) >= 2:
        return GateResult("Not AI-native", GateStatus.FAIL, f"AI-native positioning signals: {', '.join(hits[:5])}.")
    return GateResult("Not AI-native", GateStatus.PASS, "No strong AI-native founding/category signal.")


def _rules_classification(company: CompanyInput, evidence: list[Evidence], text: str, profile: CriteriaProfile) -> Classification:
    ai_hits = keyword_hits(f" {text} ", AI_KEYWORDS)
    thin_hits = keyword_hits(text, THIN_AI_KEYWORDS)
    deep_hits = keyword_hits(text, DEEP_AI_KEYWORDS)
    native_hits = keyword_hits(text, AI_NATIVE_KEYWORDS)
    data_hits = keyword_hits(text, DATA_WORKFLOW_KEYWORDS)
    urgency_hits = keyword_hits(text, URGENCY_KEYWORDS)
    feasibility_hits = keyword_hits(text, FEASIBILITY_KEYWORDS)
    anchor = _vertical_anchor(company, text, profile)

    if len(native_hits) >= 2:
        ai_posture = 5
    elif len(deep_hits) >= 5 and len(ai_hits) >= 3:
        ai_posture = 4
    elif len(deep_hits) >= 2 and len(ai_hits) >= 2:
        ai_posture = 3
    elif thin_hits:
        ai_posture = 2
    elif ai_hits:
        ai_posture = 1
    else:
        ai_posture = 0

    raw_data_workflow = min(5, max(0, len(set(data_hits)) // 2))
    if anchor.anchored:
        # An anchored vertical incumbent: the data is genuine domain depth
        # ("proprietary operational data inside recurring customer workflows"),
        # so award full moat credit plus a focus bonus for clear specialization.
        data_workflow = min(5, raw_data_workflow + 1)
    elif anchor.scale_hits or len(anchor.distinct) >= VERTICAL_SCATTER_MIN or len(anchor.weak_hits) >= 2:
        # Horizontal: unbounded-scale language, or many name-dropped verticals
        # with no anchor, or repeated soft-breadth phrasing. Broad data breadth
        # without vertical focus is not the ICP ("vertical software incumbents,
        # not broad SaaS"), so cap the moat. Scattered vertical mentions no longer
        # earn the focus bonus — that was the broad-SaaS leak.
        data_workflow = min(3, raw_data_workflow)
    else:
        # Neither anchored nor self-described as horizontal: stay neutral.
        data_workflow = raw_data_workflow
    commercial_urgency = min(5, len(set(urgency_hits)) + (1 if ai_posture in {0, 1, 2} else 0))
    budget_access = _budget_points(company, text, profile)
    feasibility = min(5, max(1 if evidence else 0, len(set(feasibility_hits)) // 2))

    return Classification(
        ai_posture=ai_posture,
        data_workflow=data_workflow,
        commercial_urgency=commercial_urgency,
        budget_access=budget_access,
        feasibility=feasibility,
        reasons={
            "ai_posture": _ai_posture_reason(ai_posture, ai_hits, thin_hits, deep_hits, native_hits),
            "data_workflow": f"Data/workflow signals: {', '.join(data_hits[:8]) or 'none found'}.",
            "commercial_urgency": f"Urgency signals: {', '.join(urgency_hits[:8]) or 'limited public urgency'}." ,
            "budget_access": "Based on employee count and public scale/funding signals.",
            "feasibility": f"Feasibility signals: {', '.join(feasibility_hits[:8]) or 'limited public implementation evidence'}.",
        },
        evidence_ids=_keyword_evidence_ids(evidence),
        confidence=0.55 if evidence else 0.25,
        source="rules",
    )


def _budget_points(company: CompanyInput, text: str, profile: CriteriaProfile) -> int:
    if company.employee_count is None:
        return 3 if any(term in text for term in ["enterprise", "trusted by", "customers", "funded"]) else 1
    if profile.min_employee_count <= company.employee_count <= profile.max_employee_count:
        return 5
    if company.employee_count > profile.max_employee_count:
        return 4
    return 2


def _ai_posture_reason(
    score: int,
    ai_hits: list[str],
    thin_hits: list[str],
    deep_hits: list[str],
    native_hits: list[str],
) -> str:
    if score == 0:
        return "No visible AI language found in fetched evidence."
    if score == 1:
        return f"Generic AI language found: {', '.join(ai_hits[:6])}."
    if score == 2:
        return f"Thin AI feature signals found: {', '.join(thin_hits[:6])}."
    if score == 3:
        return f"Grounded assistant signals found: {', '.join(deep_hits[:6])}."
    if score == 4:
        return f"Embedded AI workflow signals found: {', '.join(deep_hits[:6])}."
    return f"AI-native signals found: {', '.join(native_hits[:6])}."


def _keyword_evidence_ids(evidence: list[Evidence]) -> dict[str, list[str]]:
    groups = {
        "ai_posture": AI_KEYWORDS + THIN_AI_KEYWORDS + DEEP_AI_KEYWORDS + AI_NATIVE_KEYWORDS,
        "data_workflow": DATA_WORKFLOW_KEYWORDS,
        "commercial_urgency": URGENCY_KEYWORDS,
        "feasibility": FEASIBILITY_KEYWORDS,
    }
    result: dict[str, list[str]] = {}
    for group, keywords in groups.items():
        ids = [item.evidence_id for item in evidence if keyword_hits(item.text, keywords)]
        result[group] = ids[:5]
    return result


def _merge_classification(rules: Classification, model: Classification | None) -> Classification:
    if model is None:
        return rules
    if model.confidence < 0.35:
        return rules
    ai_posture = _clamp_int(model.ai_posture, 0, 5)
    data_workflow = _clamp_int(model.data_workflow, 0, 5)
    commercial_urgency = _clamp_int(model.commercial_urgency, 0, 5)
    budget_access = _clamp_int(model.budget_access, 0, 5)
    feasibility = _clamp_int(model.feasibility, 0, 5)
    return Classification(
        ai_posture=ai_posture,
        data_workflow=data_workflow,
        commercial_urgency=commercial_urgency,
        budget_access=budget_access,
        feasibility=feasibility,
        reasons=_model_reasons(
            model,
            {
                "ai_posture": ai_posture,
                "data_workflow": data_workflow,
                "commercial_urgency": commercial_urgency,
                "budget_access": budget_access,
                "feasibility": feasibility,
            },
        ),
        evidence_ids={**rules.evidence_ids, **model.evidence_ids},
        confidence=min(1.0, max(0.0, model.confidence)),
        source=model.source,
        ai_narrative=model.ai_narrative,
    )


def _model_reasons(model: Classification, scores: dict[str, int]) -> dict[str, str]:
    labels = {
        "ai_posture": "AI posture",
        "data_workflow": "Data/workflow",
        "commercial_urgency": "Commercial urgency",
        "budget_access": "Budget/access",
        "feasibility": "Feasibility",
    }
    reasons: dict[str, str] = {}
    for key, label in labels.items():
        reason = model.reasons.get(key)
        if reason:
            reasons[key] = reason
        else:
            reasons[key] = f"{label} scored {scores[key]}/5 by {model.source}; no detailed reason returned."
    return reasons


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return min(maximum, max(minimum, int(value)))


def _ai_gap_points(ai_posture: int) -> int:
    mapping = {0: 30, 1: 26, 2: 22, 3: 14, 4: 4, 5: 0}
    return mapping.get(ai_posture, 0)


def _gate_warnings(gates: list[GateResult]) -> list[str]:
    return [f"Manual review: {gate.name} is unknown ({gate.reason})" for gate in gates if gate.status == GateStatus.UNKNOWN]
