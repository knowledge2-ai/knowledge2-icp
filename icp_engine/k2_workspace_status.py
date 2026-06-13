from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from .k2_client import K2ApiError, K2RestClient
from .k2_workspace import AGENTS, CORPORA, DEFAULT_PROJECT_NAME, DEFAULT_SUMMARY_PATH, FEEDS


PIPELINE_SPEC_NAME = "ICP Expansion Pipeline"


class WorkspaceStatusClient(Protocol):
    def list_projects(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_corpora(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_agents(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_feeds(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_pipeline_specs(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...


def build_k2_workspace_status(
    *,
    client: WorkspaceStatusClient | None = None,
    env: dict[str, str] | None = None,
    project_name: str | None = None,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    env_values = env if env is not None else os.environ
    selected_summary_path = summary_path or Path(env_values.get("K2_ICP_WORKSPACE_SUMMARY") or DEFAULT_SUMMARY_PATH)
    summary = _load_summary(selected_summary_path)
    selected_project_name = (
        project_name
        or env_values.get("K2_ICP_PROJECT_NAME")
        or str(summary.get("project", {}).get("name") or "")
        or DEFAULT_PROJECT_NAME
    )
    base_url = env_values.get("K2_BASE_URL") or "https://api.knowledge2.ai"
    api_key = (env_values.get("K2_API_KEY") or env_values.get("K2_DEV_TOKEN") or "").strip()
    research_corpus_id = str(env_values.get("K2_RESEARCH_CORPUS_ID") or "").strip()

    if client is None and api_key:
        client = K2RestClient(api_key=api_key, base_url=base_url)

    status = _blueprint_status(
        project_name=selected_project_name,
        base_url=base_url,
        configured=bool(client),
        research_corpus_id=research_corpus_id,
    )
    if client is not None:
        try:
            return _live_status(
                client,
                status=status,
                project_name=selected_project_name,
                base_url=base_url,
                research_corpus_id=research_corpus_id,
            )
        except K2ApiError as exc:
            status["source"] = "error"
            status["warnings"].append(f"K2 API status lookup failed: {exc}")
            if exc.body:
                status["warnings"].append(exc.body[:500])
            return status

    if summary:
        return _summary_status(
            summary,
            status=status,
            project_name=selected_project_name,
            base_url=base_url,
            research_corpus_id=research_corpus_id,
        )

    status["warnings"].append("K2_API_KEY or K2_DEV_TOKEN is not configured; showing expected workspace blueprint.")
    return status


def _live_status(
    client: WorkspaceStatusClient,
    *,
    status: dict[str, Any],
    project_name: str,
    base_url: str,
    research_corpus_id: str,
) -> dict[str, Any]:
    projects = client.list_projects(limit=100, offset=0)
    project = _find_by_name(projects, project_name)
    result = {
        **status,
        "source": "k2_api",
        "base_url": base_url,
        "configured": True,
        "research_corpus_id": research_corpus_id,
        "research_corpus_configured": bool(research_corpus_id),
        "project": _record_row({"name": project_name}, project),
        "warnings": [],
    }
    project_id = _record_id(project)
    if not project_id:
        result["warnings"].append(f"K2 project '{project_name}' was not found.")
        return result

    result["corpora"] = _rows_from_records(_corpus_blueprints(), client.list_corpora(project_id, limit=100, offset=0))
    result["agents"] = _rows_from_records(_agent_blueprints(), client.list_agents(project_id, limit=100, offset=0), status_key="status")
    result["feeds"] = _rows_from_records(_feed_blueprints(), client.list_feeds(project_id, limit=100, offset=0))
    result["pipeline_spec"] = _record_row(
        {"key": "pipeline_spec", "name": PIPELINE_SPEC_NAME, "description": "K2-native ICP expansion graph."},
        _find_by_name(client.list_pipeline_specs(project_id, limit=100, offset=0), PIPELINE_SPEC_NAME),
    )
    result["warnings"].extend(_missing_warnings(result))
    return result


def _summary_status(
    summary: dict[str, Any],
    *,
    status: dict[str, Any],
    project_name: str,
    base_url: str,
    research_corpus_id: str,
) -> dict[str, Any]:
    project = summary.get("project") if isinstance(summary.get("project"), dict) else {}
    result = {
        **status,
        "source": "summary",
        "base_url": base_url,
        "configured": False,
        "research_corpus_id": research_corpus_id,
        "research_corpus_configured": bool(research_corpus_id),
        "project": _record_row({"name": project_name}, project),
        "corpora": _rows_from_mapping(_corpus_blueprints(), summary.get("corpora")),
        "agents": _rows_from_mapping(_agent_blueprints(), summary.get("agents"), status_key="status"),
        "feeds": _rows_from_mapping(_feed_blueprints(), summary.get("feeds")),
        "pipeline_spec": _record_row(
            {"key": "pipeline_spec", "name": PIPELINE_SPEC_NAME, "description": "K2-native ICP expansion graph."},
            summary.get("pipeline_spec") if isinstance(summary.get("pipeline_spec"), dict) else None,
        ),
        "warnings": ["K2 credentials are not configured; showing the latest bootstrap summary."],
    }
    result["warnings"].extend(_missing_warnings(result))
    return result


def _blueprint_status(
    *,
    project_name: str,
    base_url: str,
    configured: bool,
    research_corpus_id: str,
) -> dict[str, Any]:
    return {
        "configured": configured,
        "source": "blueprint",
        "base_url": base_url,
        "project_name": project_name,
        "project": {"key": "project", "name": project_name, "id": "", "status": "expected", "description": ""},
        "corpora": [_expected_row(item) for item in _corpus_blueprints()],
        "agents": [_expected_row(item) for item in _agent_blueprints()],
        "feeds": [_expected_row(item) for item in _feed_blueprints()],
        "pipeline_spec": _expected_row(
            {"key": "pipeline_spec", "name": PIPELINE_SPEC_NAME, "description": "K2-native ICP expansion graph."}
        ),
        "research_corpus_id": research_corpus_id,
        "research_corpus_configured": bool(research_corpus_id),
        "warnings": [],
    }


def _corpus_blueprints() -> list[dict[str, Any]]:
    return [{"key": item.key, "name": item.name, "description": item.description} for item in CORPORA]


def _agent_blueprints() -> list[dict[str, Any]]:
    return [{"key": str(item["key"]), "name": str(item["name"]), "description": str(item["description"])} for item in AGENTS]


def _feed_blueprints() -> list[dict[str, Any]]:
    return [{"key": str(item["key"]), "name": str(item["name"]), "description": str(item["description"])} for item in FEEDS]


def _rows_from_records(
    blueprints: list[dict[str, Any]],
    records: list[dict[str, Any]],
    *,
    status_key: str | None = None,
) -> list[dict[str, Any]]:
    return [_record_row(blueprint, _find_by_name(records, str(blueprint["name"])), status_key=status_key) for blueprint in blueprints]


def _rows_from_mapping(
    blueprints: list[dict[str, Any]],
    records: Any,
    *,
    status_key: str | None = None,
) -> list[dict[str, Any]]:
    mapping = records if isinstance(records, dict) else {}
    return [_record_row(blueprint, mapping.get(blueprint["key"]), status_key=status_key) for blueprint in blueprints]


def _record_row(
    blueprint: dict[str, Any],
    record: Any,
    *,
    status_key: str | None = None,
) -> dict[str, Any]:
    if not isinstance(record, dict) or not _record_id(record):
        return {**_expected_row(blueprint), "status": "missing" if record is None else "unknown"}
    return {
        "key": blueprint.get("key") or "",
        "name": str(record.get("name") or blueprint.get("name") or ""),
        "id": _record_id(record),
        "status": str(record.get(status_key) or "found") if status_key else "found",
        "description": str(record.get("description") or blueprint.get("description") or ""),
    }


def _expected_row(blueprint: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": str(blueprint.get("key") or ""),
        "name": str(blueprint.get("name") or ""),
        "id": "",
        "status": "expected",
        "description": str(blueprint.get("description") or ""),
    }


def _find_by_name(records: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((record for record in records if record.get("name") == name), None)


def _record_id(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    return str(record.get("id") or record.get("uuid") or "")


def _load_summary(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _missing_warnings(status: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for group in ("corpora", "agents", "feeds"):
        for item in status.get(group, []):
            if isinstance(item, dict) and item.get("status") in {"missing", "unknown"}:
                warnings.append(f"Missing K2 {group[:-1]}: {item.get('name')}")
    pipeline = status.get("pipeline_spec")
    if isinstance(pipeline, dict) and pipeline.get("status") in {"missing", "unknown"}:
        warnings.append(f"Missing K2 pipeline spec: {pipeline.get('name')}")
    return warnings
