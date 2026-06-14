from __future__ import annotations

from pathlib import Path
from typing import Any

from ..seed_defaults import SEED_RUN_ID
from ..tenant import TenantConfig
from ._config import ConfigMixin
from ._criteria import CriteriaMixin
from ._engagement import EngagementMixin
from ._leads import LeadsMixin
from ._platform import PlatformMixin
from ._sources import SourcesMixin
from ._helpers import (
    DEFAULT_ICP_PATH,
    DEFAULT_STATE_DIR,
    LEAD_STATUSES,
    _local_collection_status,
    provider_status,
)


class AppStore(CriteriaMixin, ConfigMixin, EngagementMixin, LeadsMixin, PlatformMixin, SourcesMixin):
    def __init__(
        self,
        state_dir: Path | str = DEFAULT_STATE_DIR,
        icp_path: Path | str = DEFAULT_ICP_PATH,
        tenant_config: TenantConfig | None = None,
    ) -> None:
        self.tenant_config = tenant_config or TenantConfig.default()
        self.state_dir = Path(state_dir)
        self.icp_path = Path(icp_path)
        self.criteria_path = self.state_dir / "criteria.md"
        self.criteria_versions_path = self.state_dir / "criteria_versions.json"
        self.prompts_path = self.state_dir / "prompts.json"
        self.settings_path = self.state_dir / "settings.json"
        self.lists_path = self.state_dir / "lists.json"
        self.lead_states_path = self.state_dir / "lead_states.json"
        self.lead_views_path = self.state_dir / "lead_views.json"
        self.audit_log_path = self.state_dir / "audit_log.json"
        self.sources_path = self.state_dir / "sources.json"
        self.source_scans_path = self.state_dir / "source_scans.json"
        self.expansion_runs_path = self.state_dir / "expansion_runs.json"
        self.provider_usage_path = self.state_dir / "provider_usage.json"
        self.quality_feedback_path = self.state_dir / "quality_feedback.json"
        self.outreach_status_path = self.state_dir / "outreach_statuses.json"
        self.eval_cases_path = self.state_dir / "eval_cases.json"
        self.eval_runs_path = self.state_dir / "eval_runs.json"
        self.query_profiles_path = self.state_dir / "query_profiles.json"
        self.runs_dir = self.state_dir / "runs"
        self.index_path = self.state_dir / "runs.json"

    def ensure(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def state(self) -> dict[str, Any]:
        runs = self.list_runs()
        summaries = [self._summary_with_workflow(item) for item in runs]
        latest_run = self.load_run(runs[0]["id"]) if runs else None
        return {
            "criteria": self.load_criteria(),
            "criteria_versions": self.list_criteria_versions(),
            "prompts": self.load_prompts(),
            "settings": self.load_settings(),
            "lists": self.load_lists(),
            "runs": summaries,
            "lead_statuses": list(LEAD_STATUSES),
            "lead_views": self.list_lead_views(),
            "sources": self.load_sources(),
            "source_scans": self.list_source_scans(limit=25),
            "expansion_runs": self.list_expansion_runs(limit=25),
            "source_coverage": self.source_coverage(),
            "provider_controls": self.provider_usage_summary(),
            "quality_feedback_summary": self.quality_feedback_summary(),
            "outreach_summary": self.outreach_summary(),
            "eval_summary": self.eval_summary(),
            "audit_log": self.list_audit_events(limit=25),
            "provider_status": provider_status(),
            "workspace_state": self.workspace_state_status(),
            "latest_run": latest_run,
        }

    def workspace_state_status(self) -> dict[str, Any]:
        self.ensure()
        return {
            "durable": True,
            "store": "local-files",
            "state_dir": str(self.state_dir),
            "collections": [
                _local_collection_status("criteria", self.criteria_path, "object"),
                _local_collection_status("criteria_versions", self.criteria_versions_path, "array"),
                _local_collection_status("settings", self.settings_path, "object"),
                _local_collection_status("sources", self.sources_path, "array"),
                _local_collection_status("source_scans", self.source_scans_path, "array"),
                _local_collection_status("expansion_runs", self.expansion_runs_path, "array"),
                _local_collection_status("provider_usage", self.provider_usage_path, "array"),
                {
                    "key": "runs",
                    "persisted": self.index_path.exists(),
                    "count": len([item for item in self.list_runs() if item.get("id") != SEED_RUN_ID]),
                    "path": str(self.index_path),
                    "type": "array",
                },
                _local_collection_status("lead_states", self.lead_states_path, "object"),
                _local_collection_status("lead_views", self.lead_views_path, "array"),
                _local_collection_status("quality_feedback", self.quality_feedback_path, "array"),
                _local_collection_status("outreach_statuses", self.outreach_status_path, "object"),
                _local_collection_status("eval_cases", self.eval_cases_path, "array"),
                _local_collection_status("eval_runs", self.eval_runs_path, "array"),
            ],
            "warnings": [],
        }

    def _summary_with_workflow(self, summary: dict[str, Any]) -> dict[str, Any]:
        run_id = str(summary.get("id") or "")
        return {
            **summary,
            "lead_status_counts": self.lead_status_counts(run_id),
            "quality_feedback_counts": self.quality_feedback_summary(run_id=run_id).get("rating_counts", {}),
            "outreach_counts": self.outreach_summary(run_id=run_id).get("status_counts", {}),
            "eval_status": self.eval_summary(run_id=run_id).get("latest_status", "not_run"),
        }
