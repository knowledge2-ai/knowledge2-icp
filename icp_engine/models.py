from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CompanyInput:
    company: str
    domain: str
    category: str = ""
    founded_year: int | None = None
    employee_count: int | None = None
    hq: str = ""
    notes: str = ""


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    url: str
    title: str
    text: str
    source_type: str = "website"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class GateResult:
    name: str
    status: GateStatus
    reason: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class Classification:
    ai_posture: int
    data_workflow: int
    commercial_urgency: int
    budget_access: int
    feasibility: int
    reasons: dict[str, str] = field(default_factory=dict)
    evidence_ids: dict[str, list[str]] = field(default_factory=dict)
    confidence: float = 0.0
    source: str = "rules"
    ai_narrative: str = ""


@dataclass
class ScoreResult:
    company: CompanyInput
    gates: list[GateResult]
    classification: Classification
    ai_gap_score: int
    data_workflow_score: int
    commercial_urgency_score: int
    budget_access_score: int
    feasibility_score: int
    total_score: int
    tier: str
    next_action: str
    ai_narrative: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def hard_gate_failed(self) -> bool:
        return any(gate.status == GateStatus.FAIL for gate in self.gates)

    @property
    def hard_gate_unknown(self) -> bool:
        return any(gate.status == GateStatus.UNKNOWN for gate in self.gates)
