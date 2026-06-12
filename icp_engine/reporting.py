from __future__ import annotations

import csv
from pathlib import Path

from .models import Evidence, GateStatus, ScoreResult
from .text import compact_snippet


def write_ranked_csv(results: list[ScoreResult], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_csv_fields())
        writer.writeheader()
        for result in sorted(results, key=lambda item: item.total_score, reverse=True):
            writer.writerow(_csv_row(result))


def write_dossier(
    results: list[ScoreResult],
    evidence_by_company: dict[str, list[Evidence]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# ICP Qualification Dossier", ""]
    for result in sorted(results, key=lambda item: item.total_score, reverse=True):
        company_key = result.company.company
        lines.extend(_company_section(result, evidence_by_company.get(company_key, [])))
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _csv_fields() -> list[str]:
    return [
        "company",
        "domain",
        "tier",
        "total_score",
        "ai_posture",
        "ai_gap_score",
        "data_workflow_score",
        "commercial_urgency_score",
        "budget_access_score",
        "feasibility_score",
        "hard_gate_failed",
        "hard_gate_unknown",
        "classification_source",
        "next_action",
        "warnings",
    ]


def _csv_row(result: ScoreResult) -> dict[str, object]:
    return {
        "company": result.company.company,
        "domain": result.company.domain,
        "tier": result.tier,
        "total_score": result.total_score,
        "ai_posture": result.classification.ai_posture,
        "ai_gap_score": result.ai_gap_score,
        "data_workflow_score": result.data_workflow_score,
        "commercial_urgency_score": result.commercial_urgency_score,
        "budget_access_score": result.budget_access_score,
        "feasibility_score": result.feasibility_score,
        "hard_gate_failed": result.hard_gate_failed,
        "hard_gate_unknown": result.hard_gate_unknown,
        "classification_source": result.classification.source,
        "next_action": result.next_action,
        "warnings": " | ".join(result.warnings),
    }


def _company_section(result: ScoreResult, evidence: list[Evidence]) -> list[str]:
    company = result.company
    lines = [
        f"## {company.company}",
        "",
        f"- Domain: {company.domain}",
        f"- Tier: {result.tier}",
        f"- Total score: {result.total_score}/100",
        f"- AI posture: {result.classification.ai_posture}/5",
        f"- Classification source: {result.classification.source}",
        f"- Next action: {result.next_action}",
        "",
        "### Hard Gates",
        "",
    ]
    for gate in result.gates:
        marker = _gate_marker(gate.status)
        lines.append(f"- {marker} {gate.name}: {gate.reason}")

    lines.extend(["", "### Score Breakdown", ""])
    lines.extend(
        [
            f"- AI gap: {result.ai_gap_score}/30",
            f"- Data/workflow moat: {result.data_workflow_score}/25",
            f"- Commercial urgency: {result.commercial_urgency_score}/20",
            f"- Budget/access: {result.budget_access_score}/15",
            f"- Feasibility: {result.feasibility_score}/10",
        ]
    )

    lines.extend(["", "### Reasoning", ""])
    for key, reason in result.classification.reasons.items():
        lines.append(f"- {key}: {reason}")

    if result.warnings:
        lines.extend(["", "### Review Flags", ""])
        for warning in result.warnings:
            lines.append(f"- {warning}")

    if evidence:
        lines.extend(["", "### Evidence", ""])
        for item in evidence[:8]:
            label = item.title or item.url
            lines.append(f"- `{item.evidence_id}` {label} ({item.url}): {compact_snippet(item.text, 320)}")

    lines.append("")
    return lines


def _gate_marker(status: GateStatus) -> str:
    if status == GateStatus.PASS:
        return "PASS"
    if status == GateStatus.FAIL:
        return "FAIL"
    return "UNKNOWN"
