from __future__ import annotations

import json
import os
from dataclasses import asdict

from .models import Classification, CompanyInput, Evidence
from .text import compact_snippet


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
    client = genai.Client(vertexai=True, project=project, location=location)
    try:
        response = client.models.generate_content(
            model=model,
            contents=_prompt(company, evidence),
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
    )


def _prompt(company: CompanyInput, evidence: list[Evidence]) -> str:
    evidence_json = [
        {
            "evidence_id": item.evidence_id,
            "url": item.url,
            "title": item.title,
            "text": compact_snippet(item.text, 1800),
        }
        for item in evidence[:10]
    ]
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
- Do not infer facts such as founding year, funding, or employee count if not present.
- Return evidence_ids that support each score.
- Keep confidence low when evidence is sparse.

Company:
{json.dumps(asdict(company), indent=2)}

Evidence:
{json.dumps(evidence_json, indent=2)}
"""
