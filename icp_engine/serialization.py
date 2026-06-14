from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from .models import Classification, CompanyInput, Evidence, GateResult, ScoreResult


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value


def company_to_dict(company: CompanyInput) -> dict[str, Any]:
    return to_jsonable(company)


def evidence_to_dict(evidence: Evidence) -> dict[str, Any]:
    return to_jsonable(evidence)


def gate_to_dict(gate: GateResult) -> dict[str, Any]:
    return to_jsonable(gate)


def classification_to_dict(classification: Classification) -> dict[str, Any]:
    return to_jsonable(classification)


def score_to_dict(result: ScoreResult) -> dict[str, Any]:
    return {
        "company": company_to_dict(result.company),
        "gates": [gate_to_dict(gate) for gate in result.gates],
        "classification": classification_to_dict(result.classification),
        "ai_gap_score": result.ai_gap_score,
        "data_workflow_score": result.data_workflow_score,
        "commercial_urgency_score": result.commercial_urgency_score,
        "budget_access_score": result.budget_access_score,
        "feasibility_score": result.feasibility_score,
        "total_score": result.total_score,
        "tier": result.tier,
        "next_action": result.next_action,
        "ai_narrative": result.ai_narrative,
        "warnings": list(result.warnings),
        "hard_gate_failed": result.hard_gate_failed,
        "hard_gate_unknown": result.hard_gate_unknown,
    }

