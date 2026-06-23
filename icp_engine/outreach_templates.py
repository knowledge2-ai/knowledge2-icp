from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OutreachTemplate:
    """A named outreach scaffold: structure + CTA the message must follow.

    ``structure`` is the ordered set of beats the LLM fills from recent evidence
    (the "scaffold + LLM fill" model). ``subject``/``body``/``cta`` are merge-field
    strings the deterministic fallback renders when Claude is unavailable, so both
    paths produce the same shape. Selection routes on persona and signal tags.
    """

    name: str
    applies_to_personas: tuple[str, ...]
    applies_to_signals: tuple[str, ...]
    structure: tuple[str, ...]
    subject: str
    body: str
    cta: str


_EXEC_AI_URGENCY = OutreachTemplate(
    name="exec-ai-urgency",
    applies_to_personas=("ceo", "founder", "chief", "president", "owner"),
    applies_to_signals=("ai-native", "generative ai", "ai posture", "ai"),
    structure=(
        "Open with the most recent, specific signal you found about the company (cite it).",
        "Raise, as an open question rather than an assertion about their plans, where the workflow data they "
        "already own could be the hardest part of an AI strategy for others to copy. Do not state what they "
        "are 'likely evaluating' as fact.",
        "Keep the value framed around THEIR evidence. Do not claim what we have done for other companies, do "
        "not call their data 'unique' or 'defensible' unless the evidence says so, and do not assert they need "
        "an 'AI advantage' as established fact.",
        "Close with one low-friction executive next step.",
    ),
    subject="{company}: where your workflow data fits an AI strategy",
    body=(
        "Hi {first_name},\n\n"
        "I was reading up on {company} and saw {evidence_line}.\n\n"
        "{angle}\n\n"
        "Most leadership teams I talk to are less stuck on 'should we do AI' and more on 'where is our own "
        "data the part that's hard to copy' — happy to share how we'd think about that for {company}.\n\n"
        "Worth a short conversation?"
    ),
    cta="Open to a 20-minute exec-level look at where {company}'s data could matter most for AI?",
)

_DATA_ADVANTAGE = OutreachTemplate(
    name="data-advantage",
    applies_to_personas=("data", "analytics", "chief data"),
    applies_to_signals=("data", "qualified-data", "workflow-data", "proprietary data", "metadata"),
    structure=(
        "Open with the recent evidence that shows they sit on meaningful proprietary/operational data — name "
        "the specific data the evidence points to.",
        "Pose the question of whether that operational data could anchor an AI capability others can't easily "
        "copy. Frame it as a hypothesis to test, not a claim about their data being 'unique' or their needing a "
        "moat. Do not cite other customers or results we have not been given.",
        "Offer a concrete, scoped way to pressure-test that question on one workflow.",
        "Close with a low-friction next step.",
    ),
    subject="{company}'s operational data and AI",
    body=(
        "Hi {first_name},\n\n"
        "Looking at {company}, {evidence_line} stood out.\n\n"
        "{angle}\n\n"
        "The question worth testing is whether that operational data could anchor AI that's hard for others "
        "to copy — {offer}\n\n"
        "Would a quick look at one high-signal workflow be useful?"
    ),
    cta="Want to compare this against one workflow where {company} already has proprietary data?",
)

_WORKFLOW_EFFICIENCY = OutreachTemplate(
    name="workflow-efficiency",
    applies_to_personas=("engineering", "product", "operations", "vp eng", "cto"),
    applies_to_signals=("workflow", "automation", "operations", "efficiency", "integration"),
    structure=(
        "Open with the recent evidence about their workflow/operations surface.",
        "Point to where AI could remove friction or unlock leverage in that workflow — phrased as a "
        "possibility grounded in the evidence, not as a claim about what we have done for similar teams.",
        "Propose a scoped, evidence-grounded way to validate the opportunity.",
        "Close with a low-friction next step.",
    ),
    subject="An AI opportunity in {company}'s workflows",
    body=(
        "Hi {first_name},\n\n"
        "I was reviewing {company} and noticed {evidence_line}.\n\n"
        "{angle}\n\n"
        "A practical next step would be {offer}\n\n"
        "Would it be useful to look at one workflow where the leverage is clearest?"
    ),
    cta="Open to a short walkthrough of one workflow where AI leverage is clearest?",
)

_DEFAULT = OutreachTemplate(
    name="default",
    applies_to_personas=(),
    applies_to_signals=(),
    structure=(
        "Open with the most recent, specific thing you found about the company (cite it).",
        "Connect it to the value narrative in the ICP criteria, grounded in what the evidence shows about "
        "THEM — not in claims about other customers, results, or social proof we have not been given.",
        "Offer a concrete, scoped, evidence-grounded next step.",
        "Close with one low-friction call to action.",
    ),
    subject="{company} AI workflow opportunity map",
    body=(
        "Hi {first_name},\n\n"
        "I was reviewing {company} and noticed {evidence_line}.\n\n"
        "{angle}\n\n"
        "A practical next step would be: {offer}\n\n"
        "Would it be useful to compare this against one workflow where {company} already has "
        "proprietary operational data?"
    ),
    cta="Share a short account-specific brief?",
)

# Ordered by selection priority: persona-driven exec first, then signal-driven.
OUTREACH_TEMPLATES: tuple[OutreachTemplate, ...] = (
    _EXEC_AI_URGENCY,
    _DATA_ADVANTAGE,
    _WORKFLOW_EFFICIENCY,
    _DEFAULT,
)


def select_template(persona: dict[str, Any] | None, signal_tags: list[str] | None) -> OutreachTemplate:
    """Pick the outreach scaffold for a contact. Persona match wins over signal
    match; falls back to the default template when nothing routes."""
    persona = persona or {}
    haystack = " ".join(
        str(persona.get(key) or "")
        for key in ("title", "role", "priority", "persona", "rationale", "angle")
    ).lower()
    tags = [str(tag).lower() for tag in (signal_tags or [])]

    for template in OUTREACH_TEMPLATES:
        if template.name == "default":
            continue
        if any(keyword in haystack for keyword in template.applies_to_personas):
            return template
    for template in OUTREACH_TEMPLATES:
        if template.name == "default":
            continue
        if any(any(keyword in tag for tag in tags) for keyword in template.applies_to_signals):
            return template
    return _DEFAULT


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def render_template(template: OutreachTemplate, context: dict[str, Any]) -> dict[str, str]:
    """Render a template's merge fields deterministically (fallback path).

    Missing context keys render empty rather than raising, so a thin lead still
    produces a coherent message.
    """
    safe = _SafeDict({key: ("" if value is None else value) for key, value in context.items()})
    return {
        "subject": template.subject.format_map(safe).strip(),
        "body": template.body.format_map(safe).strip(),
        "cta": template.cta.format_map(safe).strip(),
    }
