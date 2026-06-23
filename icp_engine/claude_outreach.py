from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from .claude import DEFAULT_MODEL, _create_message, _int_env, _tool_payload
from .evidence import select_prompt_evidence
from .models import CompanyInput, Evidence
from .outreach_templates import OutreachTemplate, select_template


# Mirrors claude.CLASSIFICATION_TOOL: a forced tool call gives us a validated,
# structured draft instead of prose we would have to parse. The judge writes
# scores; this writes the first-touch email for one buying-committee contact.
WRITE_OUTREACH_TOOL = {
    "name": "write_outreach",
    "description": "Write a personalized first-touch outreach email for one buying-committee contact.",
    "input_schema": {
        "type": "object",
        "required": ["subject", "body", "cta", "angle"],
        "properties": {
            "subject": {"type": "string", "description": "Specific, non-generic subject line tied to this company."},
            "body": {
                "type": "string",
                "description": "Email body, 3-5 short sentences, grounded only in the supplied evidence and account context. No fabricated facts, metrics, or names.",
            },
            "cta": {"type": "string", "description": "One concrete, low-friction next step."},
            "angle": {"type": "string", "description": "One sentence naming the personalization angle used."},
        },
    },
}


def generate_outreach(
    company: CompanyInput,
    persona: dict[str, Any],
    evidence: list[Evidence],
    *,
    role: str = "",
    account_context: str = "",
    criteria_markdown: str = "",
    signal_tags: list[str] | None = None,
    config: dict[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, str]:
    """Draft a personalized outreach email for one contact with Claude.

    Mirrors ``claude.classify_with_claude``: the seller voice and ICP framing come
    from the versioned ``criteria_markdown`` (not hardcoded), the message is
    grounded in the recency-filtered scraped ``evidence`` plus optional K2-retrieved
    ``account_context``, and follows the structure of the outreach template selected
    from the contact's persona and ``signal_tags`` (scaffold + LLM fill). A forced
    tool call returns a validated draft. Raises ``ClaudeUnavailable`` when the SDK or
    key is missing so callers can fall back to the deterministic template.
    """
    model = os.environ.get("ICP_CLAUDE_MODEL", DEFAULT_MODEL)
    max_tokens = _int_env("ICP_OUTREACH_MAX_TOKENS", 700)
    template = select_template(persona, signal_tags)
    system_prompt = _system_prompt(criteria_markdown)
    user_prompt = _outreach_prompt(company, persona, evidence, role, account_context, template)
    _write_prompt_debug(company.company, f"{system_prompt}\n\n{user_prompt}")

    response = _create_message(
        client,
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        user_prompt=user_prompt,
        tool=WRITE_OUTREACH_TOOL,
    )
    payload = _tool_payload(response, WRITE_OUTREACH_TOOL["name"])
    return {
        "subject": str(payload.get("subject", "")).strip(),
        "body": str(payload.get("body", "")).strip(),
        "cta": str(payload.get("cta", "")).strip(),
        "angle": str(payload.get("angle", "")).strip(),
        "template": template.name,
        "model": f"claude:{model}",
    }


def _system_prompt(criteria_markdown: str) -> str:
    rubric = criteria_markdown.strip() or "(no criteria provided)"
    return f"""You are a B2B GTM rep writing a first-touch outreach email for a single contact.
The ICP criteria below describe who we sell to and the value narrative; use it for voice and framing.

ICP CRITERIA (authoritative, versioned):
{rubric}

Rules:
- Ground every claim in the provided Evidence and Account context. Do NOT invent facts, metrics, headcount, funding, customer names, or product details.
- Do NOT fabricate sender-side social proof. No "we've helped similar companies", "companies like yours", named customers, case studies, ROI figures, or percentage gains unless that exact claim appears in the ICP CRITERIA or Evidence. When you have no concrete proof point, lead with an observation about THEM, not a claim about us.
- Do NOT assert the contact's title, seniority, or responsibilities as established fact — the role is an inference. Speak to what someone in that role typically owns ("if you own ...", "the team running ..."), not "as VP of Operations, you ...".
- Personalize on the MOST RECENT relevant signal. Do not anchor on stale or years-old news — fresh evidence is ranked first and carries a published_at date; lead with it.
- Follow the supplied message template structure (one beat per sentence, in order).
- Speak to this specific contact's role and what they own. Keep it to 3-5 short sentences.
- Be concrete and human, not salesy. No performative flattery, no buzzword stacking.
- End with one low-friction call to action.
- Call the write_outreach tool with subject, body, cta, and the personalization angle you used."""


def _outreach_prompt(
    company: CompanyInput,
    persona: dict[str, Any],
    evidence: list[Evidence],
    role: str,
    account_context: str,
    template: OutreachTemplate,
) -> str:
    evidence_json = [item.__dict__ for item in select_prompt_evidence(evidence, limit=6, snippet_chars=700)]
    contact = {
        "role": role or str(persona.get("role") or persona.get("priority") or ""),
        "title": str(persona.get("title") or ""),
        "what_they_own": str(persona.get("rationale") or persona.get("angle") or ""),
    }
    structure = "\n".join(f"  {index}. {beat}" for index, beat in enumerate(template.structure, start=1))
    return (
        "Company:\n"
        f"{json.dumps(asdict(company), indent=2)}\n\n"
        "Contact (buying-committee role to write to):\n"
        f"{json.dumps(contact, indent=2)}\n\n"
        "Account context (retrieved from our K2 corpus; empty if none):\n"
        f"{account_context.strip() or '(none)'}\n\n"
        "Evidence (scraped public pages; each item has a published_at date — prefer the most recent, "
        "and do NOT cite anything that reads as stale/years-old):\n"
        f"{json.dumps(evidence_json, indent=2)}\n\n"
        f"Message template to follow ({template.name}) — write one short sentence per beat, in order:\n"
        f"{structure}\n"
        f"Suggested call to action to adapt naturally: {template.cta.format(company=company.company)}"
    )


def _write_prompt_debug(company_name: str, prompt: str) -> None:
    debug_dir = os.environ.get("ICP_DEBUG_PROMPT_DIR")
    if not debug_dir:
        return
    from pathlib import Path

    safe_name = "".join(char.lower() if char.isalnum() else "-" for char in company_name).strip("-")
    path = Path(debug_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{safe_name or 'company'}.outreach.prompt.txt").write_text(prompt, encoding="utf-8")
