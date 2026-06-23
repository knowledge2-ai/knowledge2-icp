from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from .evidence import select_prompt_evidence
from .models import Classification, CompanyInput, Evidence


OUTREACH_SCHEMA = {
    "type": "OBJECT",
    "required": ["subject", "body", "cta", "angle"],
    "properties": {
        "subject": {"type": "STRING"},
        "body": {"type": "STRING"},
        "cta": {"type": "STRING"},
        "angle": {"type": "STRING"},
    },
}


RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "required": [
        "ai_posture",
        "data_workflow",
        "commercial_urgency",
        "budget_access",
        "feasibility",
        "confidence",
        "reasons",
        "evidence_ids",
        "ai_narrative",
    ],
    "properties": {
        "ai_posture": {"type": "INTEGER"},
        "data_workflow": {"type": "INTEGER"},
        "commercial_urgency": {"type": "INTEGER"},
        "budget_access": {"type": "INTEGER"},
        "feasibility": {"type": "INTEGER"},
        "confidence": {"type": "NUMBER"},
        "reasons": {"type": "OBJECT"},
        "evidence_ids": {"type": "OBJECT"},
        "ai_narrative": {"type": "STRING"},
    },
}


class GeminiUnavailable(RuntimeError):
    pass


def classify_with_gemini(company: CompanyInput, evidence: list[Evidence]) -> Classification:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiUnavailable("Install optional dependency with `pip install .[gemini]`.") from exc

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not project or not credentials:
        raise GeminiUnavailable(
            "Set GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_CLOUD_PROJECT to enable Gemini."
        )

    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    thinking_budget = int(os.environ.get("GEMINI_THINKING_BUDGET", "0"))
    prompt = _prompt(company, evidence)
    _write_prompt_debug(company.company, prompt)
    client = genai.Client(vertexai=True, project=project, location=location)
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=RESPONSE_SCHEMA,
                temperature=0.1,
                thinking_config=types.ThinkingConfig(
                    include_thoughts=False,
                    thinking_budget=thinking_budget,
                ),
            ),
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    payload = json.loads(response.text)
    return Classification(
        ai_posture=int(payload["ai_posture"]),
        data_workflow=int(payload["data_workflow"]),
        commercial_urgency=int(payload["commercial_urgency"]),
        budget_access=int(payload["budget_access"]),
        feasibility=int(payload["feasibility"]),
        reasons={str(k): str(v) for k, v in dict(payload.get("reasons", {})).items()},
        evidence_ids={
            str(k): [str(item) for item in value]
            for k, value in dict(payload.get("evidence_ids", {})).items()
            if isinstance(value, list)
        },
        confidence=float(payload["confidence"]),
        source=f"gemini:{model}",
        ai_narrative=str(payload.get("ai_narrative", "")),
    )


def generate_outreach(
    company: CompanyInput,
    persona: dict[str, Any],
    evidence: list[Evidence],
    *,
    role: str = "",
    account_context: str = "",
    criteria_markdown: str = "",
    signal_tags: list[str] | None = None,
) -> dict[str, str]:
    """Draft a personalized first-touch email with Gemini-on-Vertex.

    Mirrors ``claude_outreach.generate_outreach`` and deliberately reuses its
    prompt builders (same seller voice, template scaffold, grounding rules) so the
    only difference is the model/transport — a keyless Vertex call vs the Anthropic
    SDK. This lets the demo produce outreach (and have it faithfulness-judged) with
    only GCP access. Raises ``GeminiUnavailable`` when the SDK or ADC env is missing
    so callers can fall back to the deterministic template.
    """
    # Imported lazily and locally to avoid a hard import cycle and to keep the
    # Claude path the single source of truth for the prompt text.
    from .claude_outreach import _outreach_prompt, _system_prompt
    from .outreach_templates import select_template

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiUnavailable("Install optional dependency with `pip install .[gemini]`.") from exc

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not project or not credentials:
        raise GeminiUnavailable(
            "Set GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_CLOUD_PROJECT to enable Gemini."
        )

    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    template = select_template(persona, signal_tags)
    system_prompt = _system_prompt(criteria_markdown)
    user_prompt = _outreach_prompt(company, persona, evidence, role, account_context, template)
    _write_prompt_debug(f"{company.company}-outreach", f"{system_prompt}\n\n{user_prompt}")

    client = genai.Client(vertexai=True, project=project, location=location)
    try:
        response = client.models.generate_content(
            model=model,
            contents=f"{system_prompt}\n\n{user_prompt}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=OUTREACH_SCHEMA,
                temperature=0.3,
            ),
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    payload = json.loads(response.text)
    return {
        "subject": str(payload.get("subject", "")).strip(),
        "body": str(payload.get("body", "")).strip(),
        "cta": str(payload.get("cta", "")).strip(),
        "angle": str(payload.get("angle", "")).strip(),
        "template": template.name,
        "model": f"gemini:{model}",
    }


def _prompt(company: CompanyInput, evidence: list[Evidence]) -> str:
    evidence_json = [item.__dict__ for item in select_prompt_evidence(evidence, limit=10, snippet_chars=900)]
    return f"""
You are scoring companies for Knowledge2's incumbent software ICP.

ICP:
- Pre-2025 incumbent software companies.
- Product company, not primarily services/consulting.
- B2B or B2B2C.
- Proprietary workflow/data assets.
- Enough budget: roughly 25-2,000 employees, or smaller only if clearly funded/high-ARR.
- Not AI-native.
- Sweet spot has AI posture 0-2: no visible AI, generic AI copy, or thin AI feature.
- AI posture 3 can be useful if the wedge is deeper workflow transformation.
- AI posture 4-5 is usually poor fit.

Score 0-5:
- ai_posture: 0 no visible AI; 1 generic AI copy; 2 thin writer/summarizer/chatbot/search/Q&A; 3 grounded mostly-read-only assistant; 4 embedded workflow AI; 5 AI-native/agentic.
- data_workflow: proprietary operational data inside recurring workflows.
- commercial_urgency: competitor/customer/board/industry pressure to ship AI.
- budget_access: enough budget, reachable buyer, customer scale.
- feasibility: APIs, docs, integrations, cloud product, permissions/security model.

Rules:
- Use only provided evidence.
- Score AI posture from the Company and Evidence sections only, not from this rubric.
- Do not infer facts such as founding year, funding, or employee count if not present.
- Do not count the word "intelligence" as AI unless the evidence explicitly says AI, artificial intelligence, machine learning, GPT, LLM, copilot, assistant, or agent.
- Return evidence_ids that support each score.
- Keep confidence low when evidence is sparse.
- ai_narrative: 1-2 sentences on what the company is building in AI, grounded ONLY in the
  evidence; if the evidence shows no visible AI, say so plainly. Do not invent product names,
  customers, or metrics that are not in the evidence.

Company:
{json.dumps(asdict(company), indent=2)}

Evidence:
{json.dumps(evidence_json, indent=2)}
"""


def _write_prompt_debug(company_name: str, prompt: str) -> None:
    debug_dir = os.environ.get("ICP_DEBUG_PROMPT_DIR")
    if not debug_dir:
        return
    from pathlib import Path

    safe_name = "".join(char.lower() if char.isalnum() else "-" for char in company_name).strip("-")
    path = Path(debug_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{safe_name or 'company'}.prompt.txt").write_text(prompt, encoding="utf-8")
