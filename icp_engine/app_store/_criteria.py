"""Criteria cluster: load/save/lint/version/restore ICP criteria and preview impact."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..criteria import build_criteria_profile
from ..criteria_editor import format_criteria_markdown, lint_criteria_markdown
from ..seed_defaults import SEEDED_CRITERIA_MARKDOWN
from ._helpers import (
    _append_unique_criteria_version,
    _criteria_impact_reason,
    _estimated_budget_score,
    _load_json_file,
    _tier_for_total,
    _tier_label_counts,
    now_iso,
    stable_hash,
)


class CriteriaMixin:
    def load_criteria(self) -> dict[str, Any]:
        self.ensure()
        if self.criteria_path.exists():
            markdown = self.criteria_path.read_text(encoding="utf-8")
            source = str(self.criteria_path)
            updated_at = datetime.fromtimestamp(self.criteria_path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
        elif self.icp_path.exists():
            markdown = self.icp_path.read_text(encoding="utf-8")
            source = str(self.icp_path)
            updated_at = datetime.fromtimestamp(self.icp_path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
        else:
            markdown = SEEDED_CRITERIA_MARKDOWN
            source = "seed:icp.md"
            updated_at = now_iso()
        return {
            "markdown": markdown,
            "source": source,
            "updated_at": updated_at,
            "hash": stable_hash(markdown),
        }

    def save_criteria(self, markdown: str) -> dict[str, Any]:
        self.ensure()
        previous = self.load_criteria()
        cleaned = format_criteria_markdown(markdown)
        history = self._criteria_history_with(previous)
        self.criteria_path.write_text(cleaned, encoding="utf-8")
        saved = self.load_criteria()
        history = _append_unique_criteria_version(history, saved)
        self.criteria_versions_path.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
        return saved

    def lint_criteria(self, markdown: str) -> dict[str, Any]:
        return lint_criteria_markdown(markdown)

    def list_criteria_versions(self) -> list[dict[str, Any]]:
        return self._criteria_history_with(self.load_criteria())

    def restore_criteria_version(self, version_id: str) -> dict[str, Any] | None:
        history = self.list_criteria_versions()
        selected = next((item for item in history if item.get("id") == version_id or item.get("hash") == version_id), None)
        if not selected:
            return None
        self.criteria_path.write_text(str(selected.get("markdown", "")), encoding="utf-8")
        return self.load_criteria()

    def criteria_impact(self, run_id: str, markdown: str) -> dict[str, Any]:
        run = self.load_run(run_id)
        if not run:
            raise ValueError("Run not found.")
        proposed_markdown = str(markdown or "")
        if not proposed_markdown.strip():
            raise ValueError("Criteria markdown is required.")
        proposed_profile = build_criteria_profile(
            proposed_markdown,
            source="criteria-impact-preview",
            criteria_hash=stable_hash(proposed_markdown),
        ).to_dict()
        current_profile = run.get("criteria", {}).get("profile")
        if not isinstance(current_profile, dict):
            criteria = self.load_criteria()
            current_profile = build_criteria_profile(
                str(criteria.get("markdown", "")),
                source=str(criteria.get("source", "")),
                criteria_hash=str(criteria.get("hash", "")),
            ).to_dict()
        leads = [lead for lead in run.get("leads", []) if isinstance(lead, dict)]
        changes: list[dict[str, Any]] = []
        current_counts = _tier_label_counts([str(lead.get("score", {}).get("tier") or "Unknown") for lead in leads])
        proposed_tiers: list[str] = []
        for lead in leads:
            score = lead.get("score", {}) if isinstance(lead.get("score"), dict) else {}
            company = score.get("company", {}) if isinstance(score.get("company"), dict) else {}
            current_tier = str(score.get("tier") or "Unknown")
            total_score = int(score.get("total_score") or 0)
            current_budget = int(score.get("budget_access_score") or 0)
            proposed_budget = _estimated_budget_score(company, proposed_profile, current_budget)
            proposed_total = max(0, min(100, total_score - current_budget + proposed_budget))
            proposed_tier = _tier_for_total(proposed_total, bool(score.get("hard_gate_failed")), proposed_profile)
            proposed_tiers.append(proposed_tier)
            if proposed_tier != current_tier or proposed_total != total_score:
                changes.append(
                    {
                        "company": str(company.get("company") or ""),
                        "domain": str(company.get("domain") or ""),
                        "current_tier": current_tier,
                        "proposed_tier": proposed_tier,
                        "current_score": total_score,
                        "proposed_score": proposed_total,
                        "score_delta": proposed_total - total_score,
                        "reason": _criteria_impact_reason(score, company, current_profile, proposed_profile, current_budget, proposed_budget),
                    }
                )
        proposed_counts = _tier_label_counts(proposed_tiers)
        warnings = list(proposed_profile.get("warnings") or [])
        if set(proposed_profile.get("priority_terms") or []) != set(current_profile.get("priority_terms") or []):
            warnings.append("Priority-term changes require a new run to fully re-score data/workflow boosts from evidence.")
        return {
            "run_id": run_id,
            "lead_count": len(leads),
            "current_profile": current_profile,
            "proposed_profile": proposed_profile,
            "lint": self.lint_criteria(proposed_markdown),
            "current_counts": current_counts,
            "proposed_counts": proposed_counts,
            "deltas": {tier: proposed_counts.get(tier, 0) - current_counts.get(tier, 0) for tier in ["A", "B", "C", "Reject", "Unknown"]},
            "changed_count": len(changes),
            "changes": sorted(changes, key=lambda item: (abs(int(item["score_delta"])), item["company"]), reverse=True)[:100],
            "warnings": warnings,
        }

    def _criteria_history_with(self, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        value = _load_json_file(self.criteria_versions_path, list)
        history = [item for item in value or [] if isinstance(item, dict) and item.get("markdown")]
        return _append_unique_criteria_version(history, criteria)
