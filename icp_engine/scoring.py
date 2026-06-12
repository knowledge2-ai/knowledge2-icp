from __future__ import annotations

import re

from .models import (
    Classification,
    CompanyInput,
    Evidence,
    GateResult,
    GateStatus,
    ScoreResult,
)
from .text import keyword_hits, normalize_whitespace


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

HIGH_PRIORITY_VERTICALS = [
    "automotive",
    "dealer",
    "dealership",
    "fleet",
    "telematics",
    "field service",
    "maintenance",
    "logistics",
    "warehouse",
    "construction",
    "property",
    "facilities",
    "insurance",
    "claims",
    "healthcare",
    "manufacturing",
    "erp",
    "compliance",
    "legal",
    "accounting",
]


def score_company(
    company: CompanyInput,
    evidence: list[Evidence],
    *,
    model_classification: Classification | None = None,
    fetch_warnings: list[str] | None = None,
) -> ScoreResult:
    text = _combined_text(company, evidence)
    gates = _hard_gates(company, evidence, text)
    classification = _merge_classification(_rules_classification(company, evidence, text), model_classification)

    ai_gap_score = _ai_gap_points(classification.ai_posture)
    data_workflow_score = round((classification.data_workflow / 5) * 25)
    commercial_urgency_score = round((classification.commercial_urgency / 5) * 20)
    budget_access_score = round((classification.budget_access / 5) * 15)
    feasibility_score = round((classification.feasibility / 5) * 10)
    total_score = ai_gap_score + data_workflow_score + commercial_urgency_score + budget_access_score + feasibility_score

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
        warnings=warnings,
    )


def _combined_text(company: CompanyInput, evidence: list[Evidence]) -> str:
    chunks = [company.company, company.domain, company.category, company.hq, company.notes]
    chunks.extend(item.text for item in evidence)
    return normalize_whitespace(" ".join(chunks)).lower()


def _hard_gates(company: CompanyInput, evidence: list[Evidence], text: str) -> list[GateResult]:
    return [
        _founded_gate(company, text),
        _keyword_gate("Product company", text, PRODUCT_KEYWORDS, SERVICES_KEYWORDS),
        _keyword_gate("B2B or B2B2C", text, B2B_KEYWORDS, []),
        _keyword_gate("Has proprietary workflow/data", text, DATA_WORKFLOW_KEYWORDS, []),
        _budget_gate(company, text),
        _not_ai_native_gate(text),
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


def _budget_gate(company: CompanyInput, text: str) -> GateResult:
    if company.employee_count is not None:
        if 25 <= company.employee_count <= 2000:
            return GateResult("Enough budget", GateStatus.PASS, f"Employee count {company.employee_count}.")
        if company.employee_count > 2000:
            return GateResult("Enough budget", GateStatus.PASS, f"Employee count {company.employee_count}; enterprise-size target.")
        return GateResult("Enough budget", GateStatus.UNKNOWN, f"Employee count {company.employee_count}; may be too small unless funded/high-ARR.")
    if any(term in text for term in ["enterprise customers", "funded", "profitable", "trusted by", "thousands of customers"]):
        return GateResult("Enough budget", GateStatus.PASS, "Public copy suggests budget or customer scale.")
    return GateResult("Enough budget", GateStatus.UNKNOWN, "No employee count or funding/customer scale found.")


def _not_ai_native_gate(text: str) -> GateResult:
    hits = keyword_hits(text, AI_NATIVE_KEYWORDS)
    if len(hits) >= 2:
        return GateResult("Not AI-native", GateStatus.FAIL, f"AI-native positioning signals: {', '.join(hits[:5])}.")
    return GateResult("Not AI-native", GateStatus.PASS, "No strong AI-native founding/category signal.")


def _rules_classification(company: CompanyInput, evidence: list[Evidence], text: str) -> Classification:
    ai_hits = keyword_hits(f" {text} ", AI_KEYWORDS)
    thin_hits = keyword_hits(text, THIN_AI_KEYWORDS)
    deep_hits = keyword_hits(text, DEEP_AI_KEYWORDS)
    native_hits = keyword_hits(text, AI_NATIVE_KEYWORDS)
    data_hits = keyword_hits(text, DATA_WORKFLOW_KEYWORDS)
    urgency_hits = keyword_hits(text, URGENCY_KEYWORDS)
    feasibility_hits = keyword_hits(text, FEASIBILITY_KEYWORDS)
    vertical_hits = keyword_hits(f"{company.category} {text}", HIGH_PRIORITY_VERTICALS)

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

    data_workflow = min(5, max(0, len(set(data_hits)) // 2))
    if vertical_hits and data_workflow < 4:
        data_workflow += 1
    commercial_urgency = min(5, len(set(urgency_hits)) + (1 if ai_posture in {0, 1, 2} else 0))
    budget_access = _budget_points(company, text)
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


def _budget_points(company: CompanyInput, text: str) -> int:
    if company.employee_count is None:
        return 3 if any(term in text for term in ["enterprise", "trusted by", "customers", "funded"]) else 1
    if 25 <= company.employee_count <= 2000:
        return 5
    if company.employee_count > 2000:
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
    return Classification(
        ai_posture=_clamp_int(model.ai_posture, 0, 5),
        data_workflow=_clamp_int(model.data_workflow, 0, 5),
        commercial_urgency=_clamp_int(model.commercial_urgency, 0, 5),
        budget_access=_clamp_int(model.budget_access, 0, 5),
        feasibility=_clamp_int(model.feasibility, 0, 5),
        reasons={**rules.reasons, **model.reasons},
        evidence_ids={**rules.evidence_ids, **model.evidence_ids},
        confidence=min(1.0, max(0.0, model.confidence)),
        source=model.source,
    )


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return min(maximum, max(minimum, int(value)))


def _ai_gap_points(ai_posture: int) -> int:
    mapping = {0: 30, 1: 26, 2: 22, 3: 14, 4: 4, 5: 0}
    return mapping.get(ai_posture, 0)


def _gate_warnings(gates: list[GateResult]) -> list[str]:
    return [f"Manual review: {gate.name} is unknown ({gate.reason})" for gate in gates if gate.status == GateStatus.UNKNOWN]
