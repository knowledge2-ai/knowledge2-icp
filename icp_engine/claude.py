from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from .evidence import select_prompt_evidence
from .models import Classification, CompanyInput, Evidence


DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Tool schema mirrors gemini.RESPONSE_SCHEMA so the Claude classification drops
# straight into scoring._merge_classification. ai_narrative is the one addition:
# a short "what are they building in AI" summary the rules engine cannot produce.
CLASSIFICATION_TOOL = {
    "name": "record_classification",
    "description": "Record the ICP classification scores and reasoning for the company.",
    "input_schema": {
        "type": "object",
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
            "ai_posture": {"type": "integer", "minimum": 0, "maximum": 5},
            "data_workflow": {"type": "integer", "minimum": 0, "maximum": 5},
            "commercial_urgency": {"type": "integer", "minimum": 0, "maximum": 5},
            "budget_access": {"type": "integer", "minimum": 0, "maximum": 5},
            "feasibility": {"type": "integer", "minimum": 0, "maximum": 5},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasons": {
                "type": "object",
                "description": "Short reason string per dimension, keyed by dimension name.",
            },
            "evidence_ids": {
                "type": "object",
                "description": "List of supporting evidence ids per dimension, keyed by dimension name.",
            },
            "ai_narrative": {
                "type": "string",
                "description": "1-2 sentences on what the company is building in AI (or that there is no visible AI).",
            },
        },
    },
}

SUGGEST_TOOL = {
    "name": "propose_criteria",
    "description": "Propose an improved ICP criteria markdown document.",
    "input_schema": {
        "type": "object",
        "required": ["markdown", "rationale", "diff_summary"],
        "properties": {
            "markdown": {"type": "string", "description": "The full proposed ICP criteria markdown."},
            "rationale": {"type": "string", "description": "Why the proposed criteria are an improvement."},
            "diff_summary": {"type": "string", "description": "Short summary of what changed vs the current criteria."},
        },
    },
}


class ClaudeUnavailable(RuntimeError):
    pass


def classify_with_claude(
    company: CompanyInput,
    evidence: list[Evidence],
    *,
    criteria_markdown: str,
    config: dict[str, Any] | None = None,
    client: Any | None = None,
) -> Classification:
    """Judge a company against the ICP with Claude.

    Mirrors ``gemini.classify_with_gemini`` but reads the ICP rubric from the
    versioned ``criteria_markdown`` instead of a hardcoded block, so the rubric
    is a first-class, tenant-configurable asset. Raises ``ClaudeUnavailable``
    when the SDK or key is missing so callers can fall back to the rules engine.
    """
    model = os.environ.get("ICP_CLAUDE_MODEL", DEFAULT_MODEL)
    max_tokens = _int_env("ICP_CLAUDE_MAX_TOKENS", 1024)
    system_prompt = _system_prompt(criteria_markdown)
    user_prompt = _classification_prompt(company, evidence)
    _write_prompt_debug(company.company, f"{system_prompt}\n\n{user_prompt}")

    response = _create_message(
        client,
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        user_prompt=user_prompt,
        tool=CLASSIFICATION_TOOL,
    )
    payload = _tool_payload(response, CLASSIFICATION_TOOL["name"])
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
        source=f"claude:{model}",
        ai_narrative=str(payload.get("ai_narrative", "")),
    )


def suggest_criteria(
    current_markdown: str,
    sample_runs: list[dict[str, Any]] | None = None,
    *,
    client: Any | None = None,
) -> dict[str, str]:
    """Ask Claude to critique the current ICP criteria and propose an improved version.

    Returns a proposal only — the caller routes it through the existing criteria
    versioning/impact-preview flow for human approval. Nothing is persisted here.
    """
    model = os.environ.get("ICP_CLAUDE_MODEL", DEFAULT_MODEL)
    max_tokens = _int_env("ICP_CLAUDE_MAX_TOKENS", 2048)
    user_prompt = _suggest_prompt(current_markdown, sample_runs or [])
    response = _create_message(
        client,
        model=model,
        max_tokens=max_tokens,
        system=_SUGGEST_SYSTEM,
        user_prompt=user_prompt,
        tool=SUGGEST_TOOL,
    )
    payload = _tool_payload(response, SUGGEST_TOOL["name"])
    return {
        "markdown": str(payload.get("markdown", "")),
        "rationale": str(payload.get("rationale", "")),
        "diff_summary": str(payload.get("diff_summary", "")),
        "model": f"claude:{model}",
    }


def _create_message(
    client: Any | None,
    *,
    model: str,
    max_tokens: int,
    system: str,
    user_prompt: str,
    tool: dict[str, Any],
) -> Any:
    active = client or _default_client()
    return active.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.1,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user_prompt}],
    )


def _default_client() -> Any:
    try:
        import anthropic
    except ImportError as exc:
        raise ClaudeUnavailable("Install optional dependency with `pip install .[claude]`.") from exc
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ClaudeUnavailable("Set ANTHROPIC_API_KEY to enable the Claude qualifier.")
    return anthropic.Anthropic(api_key=api_key)


def _tool_payload(response: Any, tool_name: str) -> dict[str, Any]:
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return dict(block.input)
    raise ClaudeUnavailable(f"Claude did not return a {tool_name} tool call.")


def _system_prompt(criteria_markdown: str) -> str:
    rubric = criteria_markdown.strip() or "(no criteria provided)"
    return f"""You score companies against the ICP criteria below for a GTM lead-generation funnel.

ICP CRITERIA (authoritative, versioned):
{rubric}

Score each dimension 0-5 and call the record_classification tool:
- ai_posture: 0 no visible AI; 1 generic AI copy; 2 thin writer/summarizer/chatbot/search/Q&A; 3 grounded mostly-read-only assistant; 4 embedded workflow AI; 5 AI-native/agentic.
- data_workflow: proprietary operational data inside recurring workflows.
- commercial_urgency: competitor/customer/board/industry pressure to ship AI.
- budget_access: enough budget, reachable buyer, customer scale.
- feasibility: APIs, docs, integrations, cloud product, permissions/security model.

Rules:
- Use only the provided Company and Evidence. Do not infer founding year, funding, or employee count if absent.
- Return evidence_ids that support each score. Keep confidence low when evidence is sparse.
- ai_narrative: 1-2 sentences on what the company is building in AI, or state there is no visible AI."""


_SUGGEST_SYSTEM = """You are refining the ICP criteria markdown used to qualify companies for a GTM funnel.
Propose an improved version that is clearer and more discriminating, preserving the document's intent and structure.
Call the propose_criteria tool with the full proposed markdown, a rationale, and a short diff summary.
Do not invent new hard gates that contradict the current intent; tighten wording, scoring guidance, and disqualifiers."""


def _classification_prompt(company: CompanyInput, evidence: list[Evidence]) -> str:
    evidence_json = [item.__dict__ for item in select_prompt_evidence(evidence, limit=10, snippet_chars=900)]
    return (
        "Company:\n"
        f"{json.dumps(asdict(company), indent=2)}\n\n"
        "Evidence:\n"
        f"{json.dumps(evidence_json, indent=2)}"
    )


def _suggest_prompt(current_markdown: str, sample_runs: list[dict[str, Any]]) -> str:
    samples = _summarize_runs(sample_runs)
    return (
        "Current ICP criteria markdown:\n"
        f"{current_markdown.strip() or '(empty)'}\n\n"
        "Recent scored outcomes (for grounding the proposal):\n"
        f"{json.dumps(samples, indent=2)}"
    )


def _summarize_runs(sample_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for run in sample_runs[:5]:
        if not isinstance(run, dict):
            continue
        leads = run.get("leads", []) if isinstance(run.get("leads"), list) else []
        summaries.append(
            {
                "run_id": run.get("id"),
                "query": run.get("query"),
                "lead_count": len(leads),
                "leads": [_summarize_lead(lead) for lead in leads[:8] if isinstance(lead, dict)],
            }
        )
    return summaries


def _summarize_lead(lead: dict[str, Any]) -> dict[str, Any]:
    score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
    company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
    return {
        "company": company.get("company"),
        "domain": company.get("domain"),
        "tier": score.get("tier"),
        "total_score": score.get("total_score"),
        "ai_posture": score.get("classification", {}).get("ai_posture") if isinstance(score.get("classification"), dict) else None,
    }


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _write_prompt_debug(company_name: str, prompt: str) -> None:
    debug_dir = os.environ.get("ICP_DEBUG_PROMPT_DIR")
    if not debug_dir:
        return
    from pathlib import Path

    safe_name = "".join(char.lower() if char.isalnum() else "-" for char in company_name).strip("-")
    path = Path(debug_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{safe_name or 'company'}.claude.prompt.txt").write_text(prompt, encoding="utf-8")
