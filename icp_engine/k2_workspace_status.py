from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from .k2_client import K2ApiError, K2RestClient
from .k2_workspace import AGENTS, CORPORA, DEFAULT_PROJECT_NAME, DEFAULT_SUMMARY_PATH, FEEDS
from .tenant import K2Settings


PIPELINE_SPEC_NAME = "ICP Expansion Pipeline"


class WorkspaceStatusClient(Protocol):
    def list_projects(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_corpora(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_agents(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_feeds(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_pipeline_specs(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...

    def discover_metadata(self, corpus_id: str, *, refresh: bool = False, include: str | None = None) -> dict[str, Any]: ...


class PipelineActionClient(WorkspaceStatusClient, Protocol):
    def dry_run_pipeline_spec(self, pipeline_spec_id: str, *, sample_input: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def apply_pipeline_spec(self, pipeline_spec_id: str, *, activate_entities: bool = True) -> dict[str, Any]: ...

    def trigger_pipeline_spec(self, pipeline_spec_id: str) -> dict[str, Any]: ...

    def backfill_pipeline_spec(self, pipeline_spec_id: str, *, start_from: str) -> dict[str, Any]: ...


def build_k2_workspace_status(
    *,
    client: WorkspaceStatusClient | None = None,
    env: dict[str, str] | None = None,
    project_name: str | None = None,
    summary_path: Path | None = None,
    k2_settings: K2Settings | None = None,
) -> dict[str, Any]:
    settings = k2_settings or K2Settings()
    env_values = env if env is not None else os.environ
    selected_summary_path = summary_path or Path(env_values.get("K2_ICP_WORKSPACE_SUMMARY") or DEFAULT_SUMMARY_PATH)
    summary = _load_summary(selected_summary_path)
    selected_project_name = (
        project_name
        or env_values.get("K2_ICP_PROJECT_NAME")
        or str(summary.get("project", {}).get("name") or "")
        or settings.project_name
    )
    base_url = env_values.get("K2_BASE_URL") or settings.base_url
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


def run_k2_pipeline_action(
    action: str,
    *,
    client: PipelineActionClient | None = None,
    env: dict[str, str] | None = None,
    project_name: str | None = None,
    summary_path: Path | None = None,
    sample_input: dict[str, Any] | None = None,
    activate_entities: bool = True,
    start_from: str | None = None,
    k2_settings: K2Settings | None = None,
) -> dict[str, Any]:
    settings = k2_settings or K2Settings()
    normalized_action = action.strip().lower().replace("-", "_")
    if normalized_action not in {"dry_run", "apply", "trigger", "backfill"}:
        raise ValueError("Unsupported K2 pipeline action. Use dry_run, apply, trigger, or backfill.")

    env_values = env if env is not None else os.environ
    selected_summary_path = summary_path or Path(env_values.get("K2_ICP_WORKSPACE_SUMMARY") or DEFAULT_SUMMARY_PATH)
    summary = _load_summary(selected_summary_path)
    selected_project_name = (
        project_name
        or env_values.get("K2_ICP_PROJECT_NAME")
        or str(summary.get("project", {}).get("name") or "")
        or settings.project_name
    )
    base_url = env_values.get("K2_BASE_URL") or settings.base_url
    api_key = (env_values.get("K2_API_KEY") or env_values.get("K2_DEV_TOKEN") or "").strip()

    if client is None:
        if not api_key:
            raise K2ApiError(
                "K2_API_KEY or K2_DEV_TOKEN is not configured; pipeline actions require live K2 credentials.",
                status_code=503,
            )
        client = K2RestClient(api_key=api_key, base_url=base_url)

    project = _find_by_name(client.list_projects(limit=100, offset=0), selected_project_name)
    project_id = _record_id(project)
    if not project_id:
        raise K2ApiError(f"K2 project '{selected_project_name}' was not found.", status_code=404)

    spec = _find_by_name(client.list_pipeline_specs(project_id, limit=100, offset=0), PIPELINE_SPEC_NAME)
    spec_id = _record_id(spec)
    if not spec_id:
        raise K2ApiError(f"K2 pipeline spec '{PIPELINE_SPEC_NAME}' was not found.", status_code=404)

    backfill_start_from = start_from or _default_backfill_start_from()
    if normalized_action == "dry_run":
        result = client.dry_run_pipeline_spec(spec_id, sample_input=sample_input)
    elif normalized_action == "apply":
        result = client.apply_pipeline_spec(spec_id, activate_entities=activate_entities)
    elif normalized_action == "trigger":
        result = client.trigger_pipeline_spec(spec_id)
    else:
        result = client.backfill_pipeline_spec(spec_id, start_from=backfill_start_from)

    payload: dict[str, Any] = {
        "status": "ok",
        "action": normalized_action,
        "project": _record_row({"key": "project", "name": selected_project_name, "description": ""}, project),
        "pipeline_spec": _record_row(
            {"key": "pipeline_spec", "name": PIPELINE_SPEC_NAME, "description": "K2-native ICP expansion graph."},
            spec,
        ),
        "result": result,
        "workspace": build_k2_workspace_status(
            client=client,
            env=dict(env_values),
            project_name=selected_project_name,
            summary_path=selected_summary_path,
            k2_settings=settings,
        ),
    }
    if normalized_action == "backfill":
        payload["backfill_start_from"] = backfill_start_from
    return payload


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
    _attach_corpus_health(result["corpora"], client)
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
    _attach_summary_corpus_health(result["corpora"], summary.get("corpora"))
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


def _attach_corpus_health(rows: list[dict[str, Any]], client: WorkspaceStatusClient) -> None:
    for row in rows:
        corpus_id = str(row.get("id") or "")
        if not corpus_id or row.get("status") in {"missing", "unknown"}:
            row["health"] = _corpus_health(status="missing")
            continue
        try:
            metadata = client.discover_metadata(corpus_id, refresh=False, include="top_values")
        except K2ApiError as exc:
            row["health"] = _corpus_health(status="error", warning=str(exc))
            continue
        row["health"] = _metadata_health(metadata)


def _attach_summary_corpus_health(rows: list[dict[str, Any]], records: Any) -> None:
    mapping = records if isinstance(records, dict) else {}
    for row in rows:
        record = mapping.get(row.get("key")) if isinstance(mapping, dict) else {}
        documents_planned = record.get("documents_planned") if isinstance(record, dict) else None
        row["health"] = _corpus_health(
            status="summary",
            total_documents=int(documents_planned or 0),
            warning="" if documents_planned else "No document count in bootstrap summary.",
        )


def _metadata_health(metadata: dict[str, Any]) -> dict[str, Any]:
    fields = metadata.get("fields") if isinstance(metadata.get("fields"), list) else []
    total_documents = _int_value(metadata.get("total_documents") or metadata.get("totalDocuments"))
    total_chunks = _int_value(metadata.get("total_chunks") or metadata.get("totalChunks"))
    status = "ready" if total_documents > 0 and fields else "empty" if total_documents == 0 else "metadata_pending"
    return _corpus_health(
        status=status,
        total_documents=total_documents,
        total_chunks=total_chunks,
        field_count=len(fields),
        sample_fields=[str(field.get("key") or field.get("name") or "") for field in fields[:8] if isinstance(field, dict)],
    )


def _corpus_health(
    *,
    status: str,
    total_documents: int = 0,
    total_chunks: int = 0,
    field_count: int = 0,
    sample_fields: list[str] | None = None,
    warning: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "total_documents": total_documents,
        "total_chunks": total_chunks,
        "field_count": field_count,
        "sample_fields": sample_fields or [],
        "warning": warning,
    }


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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
        "health": _corpus_health(status="not_configured"),
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


def _default_backfill_start_from() -> str:
    value = datetime.now(timezone.utc) - timedelta(days=30)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
