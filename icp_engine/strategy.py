from __future__ import annotations

from .models import Evidence, ScoreResult
from .text import keyword_hits


PRODUCT_PERSONAS = [
    {
        "title": "Chief Product Officer",
        "priority": "primary",
        "rationale": "Owns AI product strategy, roadmap tradeoffs, and customer-facing differentiation.",
        "apollo_titles": ["chief product officer", "vp product", "head of product"],
    },
    {
        "title": "VP Engineering",
        "priority": "primary",
        "rationale": "Owns feasibility, integration architecture, and delivery capacity for workflow AI.",
        "apollo_titles": ["vp engineering", "head of engineering", "chief technology officer"],
    },
    {
        "title": "Chief Data Officer",
        "priority": "secondary",
        "rationale": "Owns proprietary data readiness, governance, and metadata quality.",
        "apollo_titles": ["chief data officer", "head of data", "vp data"],
    },
]

VERTICAL_PERSONAS = {
    "automotive": "VP Product, Connected Services",
    "dealer": "GM of Dealer Platform",
    "fleet": "VP Fleet Product",
    "insurance": "Head of Claims Product",
    "healthcare": "VP Patient Operations",
    "construction": "VP Platform Product",
    "property": "Head of Resident Experience",
    "legal": "Head of Legal Tech Strategy",
    "accounting": "VP Practice Platform",
}


COMMITTEE_ROLES = ("economic_buyer", "champion", "technical_evaluator", "blocker")


def build_strategy(result: ScoreResult, evidence: list[Evidence], metadata: dict[str, object] | None = None) -> dict[str, object]:
    evidence_text = " ".join(item.text for item in evidence).lower()
    vertical_hits = keyword_hits(f"{result.company.category} {evidence_text}", list(VERTICAL_PERSONAS.keys()))
    ai_posture = result.classification.ai_posture
    metadata = metadata or {}

    wedge = _wedge(ai_posture, result.total_score)
    urgency = _urgency(result, evidence_text)
    offer = _offer(result, vertical_hits)
    objections = _objections(result)

    personas = recommended_personas(result, vertical_hits, metadata)
    committee = build_buying_committee(result, personas)
    return {
        "headline": f"{result.company.company}: {wedge}",
        "wedge": wedge,
        "urgency": urgency,
        "offer": offer,
        "outreach_angle": _outreach_angle(result, vertical_hits),
        "first_step": _first_step(result),
        "objections": objections,
        "personas": personas,
        "committee": committee,
        "apollo_titles": sorted({title for persona in personas for title in persona.get("apollo_titles", [])}),
    }


def build_buying_committee(result: ScoreResult, personas: list[dict[str, object]]) -> list[dict[str, object]]:
    """Map the recommended personas into a structured buying committee.

    Turns the flat persona list into the four canonical B2B buying roles
    (economic buyer / champion / technical evaluator / blocker), each carrying the
    Apollo titles to prospect for and the angle to lead with. Deterministic and
    rule-based so it always renders even with no LLM; the per-contact message is
    where Claude personalizes (see ``claude_outreach``). Empty when there are no
    personas to map (e.g. a rejected lead).
    """
    if not personas:
        return []

    champion = _select_persona(personas, ["product", "general manager", "platform", "resident", "claims", "patient"])
    technical = _select_persona(personas, ["engineering", "technology", "cto", "data", "tech"])
    economic = _select_persona(personas, ["ceo", "founder", "president", "chief product"]) or champion
    objections = _objections(result)

    committee = [
        _committee_role("economic_buyer", economic, _economic_angle(result)),
        _committee_role("champion", champion, _champion_angle(result)),
    ]
    if technical and technical is not champion:
        committee.append(_committee_role("technical_evaluator", technical, _technical_angle(result)))
    blocker = _select_persona(personas, ["data", "chief data", "security", "governance"])
    if blocker is not None and all(blocker is not chosen for chosen in (economic, champion, technical)):
        committee.append(_committee_role("blocker", blocker, objections[0] if objections else _blocker_angle(result)))
    return committee


def _select_persona(personas: list[dict[str, object]], needles: list[str]) -> dict[str, object] | None:
    for persona in personas:
        haystack = " ".join(
            [
                str(persona.get("title") or ""),
                " ".join(str(item) for item in persona.get("apollo_titles", []) if item),
            ]
        ).lower()
        if any(needle in haystack for needle in needles):
            return persona
    return None


def _committee_role(role: str, persona: dict[str, object] | None, angle: str) -> dict[str, object]:
    persona = persona or {}
    return {
        "role": role,
        "title": str(persona.get("title") or _ROLE_FALLBACK_TITLE[role]),
        "priority": str(persona.get("priority") or "primary"),
        "apollo_titles": list(persona.get("apollo_titles") or _ROLE_FALLBACK_TITLES[role]),
        "rationale": str(persona.get("rationale") or ""),
        "angle": angle,
    }


_ROLE_FALLBACK_TITLE = {
    "economic_buyer": "Chief Product Officer",
    "champion": "VP Product",
    "technical_evaluator": "VP Engineering",
    "blocker": "Chief Data Officer",
}

_ROLE_FALLBACK_TITLES = {
    "economic_buyer": ["chief product officer", "ceo", "founder"],
    "champion": ["vp product", "head of product"],
    "technical_evaluator": ["vp engineering", "chief technology officer"],
    "blocker": ["chief data officer", "head of data"],
}


def _economic_angle(result: ScoreResult) -> str:
    if result.tier == "A":
        return "Frame the AI opportunity as category positioning and revenue, not a feature; this score justifies an executive narrative."
    return "Tie the workflow-AI wedge to a budget owner: quantify the customer or revenue exposure of standing still."


def _champion_angle(result: ScoreResult) -> str:
    if result.classification.ai_posture <= 1:
        return "Give the product owner a concrete first workflow where proprietary data becomes a visible AI advantage."
    return "Help the product owner move from feature-level AI to metadata-grounded automation customers can trust."


def _technical_angle(result: ScoreResult) -> str:
    return "Speak to feasibility: integration surface, permissions/security model, and delivery capacity for workflow AI."


def _blocker_angle(result: ScoreResult) -> str:
    return "Pre-empt the governance objection: data readiness, evals, and reliability before any production AI claim."


def recommended_personas(
    result: ScoreResult,
    vertical_hits: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    personas = [dict(item) for item in PRODUCT_PERSONAS]
    vertical_hits = vertical_hits or []
    if vertical_hits:
        label = VERTICAL_PERSONAS[vertical_hits[0]]
        personas.insert(
            0,
            {
                "title": label,
                "priority": "primary",
                "rationale": f"Vertical owner likely cares about {vertical_hits[0]} workflow depth and AI differentiation.",
                "apollo_titles": [label.lower(), "vp product", "general manager"],
            },
        )
    if result.tier == "A":
        personas.append(
            {
                "title": "CEO or Founder",
                "priority": "executive",
                "rationale": "Tier A score justifies an executive narrative around AI urgency and category positioning.",
                "apollo_titles": ["ceo", "founder", "president"],
            }
        )
    return personas[:5]


def _wedge(ai_posture: int, total_score: int) -> str:
    if ai_posture <= 1 and total_score >= 70:
        return "turn proprietary workflow data into a visible AI product narrative"
    if ai_posture == 2:
        return "upgrade shallow AI features into governed workflow automation"
    if ai_posture == 3:
        return "move from read-only assistant to action-capable workflow AI"
    if ai_posture >= 4:
        return "evaluate AI governance, reliability, and metadata quality"
    return "validate whether the company has enough workflow depth for AI expansion"


def _urgency(result: ScoreResult, evidence_text: str) -> str:
    if result.commercial_urgency_score >= 14:
        return "Public evidence suggests competitive pressure, automation pressure, or customer-experience urgency."
    if "competitor" in evidence_text or "automation" in evidence_text:
        return "Use competitor and automation pressure as the opening trigger."
    return "Lead with a category benchmark: peers are adding AI, but durable differentiation depends on proprietary workflow data."


def _offer(result: ScoreResult, vertical_hits: list[str]) -> str:
    vertical = vertical_hits[0] if vertical_hits else result.company.category or "their core workflow"
    if result.tier == "A":
        return f"Propose a 2-week AI opportunity map for {vertical}, grounded in existing product data and metadata."
    if result.tier == "B":
        return f"Offer a lightweight discovery workshop to identify one metadata-rich {vertical} workflow worth prototyping."
    return "Nurture with market education until budget, workflow depth, or urgency is clearer."


def _outreach_angle(result: ScoreResult, vertical_hits: list[str]) -> str:
    vertical = vertical_hits[0] if vertical_hits else "workflow"
    if result.classification.ai_posture <= 1:
        return f"You appear to have meaningful {vertical} data but limited public AI positioning. That gap can become a product advantage."
    if result.classification.ai_posture == 2:
        return "Your public AI story looks feature-level. The next step is metadata-grounded automation customers can trust."
    return "Your public AI story exists; the opportunity is stronger governance, evals, and action workflows."


def _first_step(result: ScoreResult) -> str:
    if result.hard_gate_failed:
        return "Do not outbound yet. Resolve failed gates or use as nurture only."
    if result.hard_gate_unknown:
        return "Run one manual research pass to resolve unknown hard gates before executive outreach."
    if result.tier == "A":
        return "Prioritize for human account research and Apollo prospect enrichment."
    return "Review manually and collect one stronger urgency trigger."


def _objections(result: ScoreResult) -> list[str]:
    objections = []
    if result.budget_access_score < 8:
        objections.append("Budget ownership may be unclear; qualify funding, ARR, or enterprise customer base.")
    if result.feasibility_score < 5:
        objections.append("Technical feasibility is not obvious; look for APIs, permissions, and integration docs.")
    if result.classification.ai_posture >= 4:
        objections.append("They may see themselves as already AI-forward; lead with governance and reliability, not first AI feature.")
    if not objections:
        objections.append("Main risk is timing: verify current AI roadmap ownership and urgency.")
    return objections
