from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .seed_defaults import SEEDED_CRITERIA_MARKDOWN, SEEDED_LISTS, SEEDED_PROMPTS, SEEDED_SETTINGS, SEED_RUN_ID, seeded_run


DEFAULT_STATE_DIR = Path(os.environ.get("ICP_APP_STATE_DIR", "out/app_state"))
DEFAULT_ICP_PATH = Path(os.environ.get("ICP_CRITERIA_PATH", "icp.md"))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class AppStore:
    def __init__(self, state_dir: Path | str = DEFAULT_STATE_DIR, icp_path: Path | str = DEFAULT_ICP_PATH) -> None:
        self.state_dir = Path(state_dir)
        self.icp_path = Path(icp_path)
        self.criteria_path = self.state_dir / "criteria.md"
        self.prompts_path = self.state_dir / "prompts.json"
        self.settings_path = self.state_dir / "settings.json"
        self.lists_path = self.state_dir / "lists.json"
        self.runs_dir = self.state_dir / "runs"
        self.index_path = self.state_dir / "runs.json"

    def ensure(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

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
        cleaned = markdown.strip() + "\n"
        self.criteria_path.write_text(cleaned, encoding="utf-8")
        return self.load_criteria()

    def load_prompts(self) -> list[dict[str, Any]]:
        self.ensure()
        value = _load_json_file(self.prompts_path, list)
        if value is None:
            return [dict(item) for item in SEEDED_PROMPTS]
        return [item for item in value if isinstance(item, dict)]

    def load_settings(self) -> dict[str, Any]:
        self.ensure()
        value = _load_json_file(self.settings_path, dict)
        if value is None:
            return dict(SEEDED_SETTINGS)
        return {**SEEDED_SETTINGS, **value}

    def load_lists(self) -> dict[str, Any]:
        self.ensure()
        value = _load_json_file(self.lists_path, dict)
        if value is None:
            return json.loads(json.dumps(SEEDED_LISTS))
        return {**json.loads(json.dumps(SEEDED_LISTS)), **value}

    def list_runs(self) -> list[dict[str, Any]]:
        self.ensure()
        if not self.index_path.exists():
            return [_run_summary(seeded_run())]
        try:
            items = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return [_run_summary(seeded_run())]
        if not isinstance(items, list):
            return [_run_summary(seeded_run())]
        return sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def save_run(self, run: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        run_id = run["id"]
        run_path = self.runs_dir / f"{run_id}.json"
        run_path.write_text(json.dumps(run, indent=2, sort_keys=True), encoding="utf-8")

        index = [item for item in self.list_runs() if item.get("id") not in {run_id, SEED_RUN_ID}]
        index.append(_run_summary(run))
        self.index_path.write_text(json.dumps(sorted(index, key=lambda item: str(item.get("created_at") or ""), reverse=True), indent=2, sort_keys=True), encoding="utf-8")
        return run

    def load_run(self, run_id: str) -> dict[str, Any] | None:
        self.ensure()
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            if run_id == SEED_RUN_ID:
                return seeded_run()
            return None
        try:
            value = json.loads(run_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def state(self) -> dict[str, Any]:
        runs = self.list_runs()
        return {
            "criteria": self.load_criteria(),
            "prompts": self.load_prompts(),
            "settings": self.load_settings(),
            "lists": self.load_lists(),
            "runs": runs,
            "provider_status": provider_status(),
            "latest_run": self.load_run(runs[0]["id"]) if runs else None,
        }


def provider_status() -> dict[str, dict[str, Any]]:
    return {
        "apollo": {
            "configured": bool(os.environ.get("APOLLO_API_KEY")),
            "env": "APOLLO_API_KEY",
        },
        "k2": {
            "configured": bool(os.environ.get("K2_API_KEY")),
            "env": "K2_API_KEY",
            "base_url": os.environ.get("K2_BASE_URL", "https://api.knowledge2.ai"),
            "research_corpus_configured": bool(os.environ.get("K2_RESEARCH_CORPUS_ID")),
        },
        "github": {
            "configured": bool(os.environ.get("GITHUB_TOKEN")),
            "env": "GITHUB_TOKEN",
            "public_fallback": True,
        },
        "search": {
            "configured": True,
            "provider": os.environ.get("ICP_SEARCH_PROVIDER", "duckduckgo-html"),
        },
    }


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    leads = run.get("leads", [])
    scores = [lead.get("score", {}).get("total_score", 0) for lead in leads]
    return {
        "id": run.get("id"),
        "query": run.get("query", ""),
        "created_at": run.get("created_at"),
        "status": run.get("status", "unknown"),
        "lead_count": len(leads),
        "top_score": max(scores) if scores else 0,
        "tier_counts": _tier_counts(leads),
        "warnings": run.get("warnings", [])[:5],
    }


def _tier_counts(leads: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lead in leads:
        tier = lead.get("score", {}).get("tier", "Unknown")
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _load_json_file(path: Path, expected_type: type) -> Any | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, expected_type) else None
