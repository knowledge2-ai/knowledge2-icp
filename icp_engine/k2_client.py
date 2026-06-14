from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .tenant import Branding


_BRANDING = Branding()


# The /search:batch endpoint hard-caps top_k server-side; mirror it here so callers
# can size their requests to what the API will actually return (no silent truncation).
SEARCH_BATCH_MAX_TOP_K = 20


class K2ApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class K2RestClient:
    api_key: str
    base_url: str = "https://api.knowledge2.ai"
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("K2 API key is required for live sync.")

    def list_projects(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v1/projects", params={"limit": limit, "offset": offset})
        return _list_from_payload(payload, "projects")

    def create_project(self, name: str) -> dict[str, Any]:
        payload = self._request("POST", "/v1/projects", body={"name": name})
        return _dict_payload(payload)

    def ensure_project(self, name: str) -> dict[str, Any]:
        for project in self.list_projects():
            if project.get("name") == name:
                return project
        return self.create_project(name)

    def list_corpora(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/v1/corpora",
            params={"project_id": project_id, "limit": limit, "offset": offset},
        )
        return _list_from_payload(payload, "corpora")

    def create_corpus(self, project_id: str, name: str, description: str = "") -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/v1/corpora",
            body={"projectId": project_id, "name": name, "description": description},
        )
        return _dict_payload(payload)

    def ensure_corpus(self, project_id: str, name: str, description: str = "") -> dict[str, Any]:
        for corpus in self.list_corpora(project_id):
            if corpus.get("name") == name:
                return corpus
        return self.create_corpus(project_id, name, description)

    def upload_documents(
        self,
        corpus_id: str,
        documents: list[dict[str, Any]],
        *,
        idempotency_key: str | None = None,
        auto_index: bool = False,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        payload = self._request(
            "POST",
            f"/v1/corpora/{corpus_id}/documents:batch",
            body={"documents": documents, "autoIndex": auto_index, "wait": False},
            headers=headers,
        )
        return _dict_payload(payload)

    def get_job(self, job_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/v1/jobs/{job_id}")
        return _dict_payload(payload)

    def sync_indexes(self, corpus_id: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        payload = self._request("POST", f"/v1/corpora/{corpus_id}/indexes:sync", headers=headers)
        return _dict_payload(payload)

    def discover_metadata(
        self,
        corpus_id: str,
        *,
        refresh: bool = False,
        include: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if refresh:
            params["refresh"] = "true"
        if include:
            params["include"] = include
        payload = self._request("GET", f"/v1/corpora/{corpus_id}/metadata/discover", params=params)
        return _dict_payload(payload)

    def search_batch(
        self,
        corpus_id: str,
        queries: list[str],
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"queries": queries, "top_k": max(1, min(top_k, SEARCH_BATCH_MAX_TOP_K))}
        if filters is not None:
            body["filters"] = filters
        payload = self._request("POST", f"/v1/corpora/{corpus_id}/search:batch", body=body)
        return _dict_payload(payload)

    def list_agents(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/v1/agents",
            params={"project_id": project_id, "limit": limit, "offset": offset},
        )
        return _list_from_payload(payload, "agents")

    def create_agent(
        self,
        *,
        project_id: str,
        name: str,
        corpus_id: str,
        description: str = "",
        task_type: str = "query",
        instructions: str | None = None,
        declared_schema: dict[str, Any] | None = None,
        harvest_policy: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "project_id": project_id,
            "name": name,
            "corpus_id": corpus_id,
            "description": description,
            "task_type": task_type,
        }
        if instructions is not None:
            body["instructions"] = instructions
        if declared_schema is not None:
            body["declared_schema"] = declared_schema
        if harvest_policy is not None:
            body["harvest_policy"] = harvest_policy
        payload = self._request("POST", "/v1/agents", body=body)
        return _dict_payload(payload)

    def ensure_agent(self, *, project_id: str, name: str, **kwargs: Any) -> dict[str, Any]:
        for agent in self.list_agents(project_id):
            if agent.get("name") == name:
                return agent
        return self.create_agent(project_id=project_id, name=name, **kwargs)

    def update_agent(
        self,
        agent_id: str,
        *,
        corpus_id: str | None = None,
        description: str | None = None,
        task_type: str | None = None,
        instructions: str | None = None,
        declared_schema: dict[str, Any] | None = None,
        harvest_policy: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if corpus_id is not None:
            body["corpus_id"] = corpus_id
        if description is not None:
            body["description"] = description
        if task_type is not None:
            body["task_type"] = task_type
        if instructions is not None:
            body["instructions"] = instructions
        if declared_schema is not None:
            body["declared_schema"] = declared_schema
        if harvest_policy is not None:
            body["harvest_policy"] = harvest_policy
        payload = self._request("PATCH", f"/v1/agents/{agent_id}", body=body)
        return _dict_payload(payload)

    def activate_agent(self, agent_id: str) -> dict[str, Any]:
        payload = self._request("POST", f"/v1/agents/{agent_id}/activate")
        return _dict_payload(payload)

    def list_feeds(self, project_id: str, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/v1/feeds",
            params={"project_id": project_id, "limit": limit, "offset": offset},
        )
        return _list_from_payload(payload, "feeds")

    def create_feed(
        self,
        *,
        project_id: str,
        name: str,
        source_agent_id: str,
        description: str = "",
        target_corpus_id: str | None = None,
        persistent: bool = False,
        reactive: bool = False,
        execution_mode: str = "retrieve",
        schedule_interval: str | None = None,
        schedule_hour: int | None = None,
        schedule_cron: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "project_id": project_id,
            "name": name,
            "source_agent_id": source_agent_id,
            "description": description,
            "persistent": persistent,
            "reactive": reactive,
            "execution_mode": execution_mode,
        }
        if target_corpus_id is not None:
            body["target_corpus"] = {"existing": target_corpus_id}
        if schedule_interval is not None:
            body["schedule_interval"] = schedule_interval
        if schedule_hour is not None:
            body["schedule_hour"] = schedule_hour
        if schedule_cron is not None:
            body["schedule_cron"] = schedule_cron
        payload = self._request("POST", "/v1/feeds", body=body)
        return _dict_payload(payload)

    def ensure_feed(self, *, project_id: str, name: str, **kwargs: Any) -> dict[str, Any]:
        for feed in self.list_feeds(project_id):
            if feed.get("name") == name:
                return feed
        return self.create_feed(project_id=project_id, name=name, **kwargs)

    def list_pipeline_specs(
        self,
        project_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/v1/pipeline-specs",
            params={"project_id": project_id, "limit": limit, "offset": offset},
        )
        return _list_from_payload(payload, "pipeline_specs")

    def create_pipeline_spec(
        self,
        *,
        project_id: str,
        name: str,
        topology: dict[str, Any],
        description: str = "",
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/v1/pipeline-specs",
            body={
                "project_id": project_id,
                "name": name,
                "description": description,
                "topology": topology,
            },
        )
        return _dict_payload(payload)

    def ensure_pipeline_spec(
        self,
        *,
        project_id: str,
        name: str,
        topology: dict[str, Any],
        description: str = "",
    ) -> dict[str, Any]:
        for spec in self.list_pipeline_specs(project_id):
            if spec.get("name") == name:
                return spec
        return self.create_pipeline_spec(
            project_id=project_id,
            name=name,
            topology=topology,
            description=description,
        )

    def dry_run_pipeline_spec(
        self,
        pipeline_spec_id: str,
        *,
        sample_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = {"sample_input": sample_input} if sample_input is not None else None
        payload = self._request("POST", f"/v1/pipeline-specs/{pipeline_spec_id}/dry-run", body=body)
        return _dict_payload(payload)

    def apply_pipeline_spec(self, pipeline_spec_id: str, *, activate_entities: bool = True) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/v1/pipeline-specs/{pipeline_spec_id}/apply",
            body={"activate_entities": activate_entities},
        )
        return _dict_payload(payload)

    def trigger_pipeline_spec(self, pipeline_spec_id: str) -> dict[str, Any]:
        payload = self._request("POST", f"/v1/pipeline-specs/{pipeline_spec_id}/trigger")
        return _dict_payload(payload)

    def backfill_pipeline_spec(self, pipeline_spec_id: str, *, start_from: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/v1/pipeline-specs/{pipeline_spec_id}/backfill",
            body={"start_from": start_from},
        )
        return _dict_payload(payload)

    def generate_answer(
        self,
        corpus_id: str,
        query: str,
        *,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "query": query,
            "topK": max(1, min(top_k, 20)),
            "hybrid": {
                "enabled": True,
                "fusionMode": "rrf",
                "metadataSparseEnabled": True,
                "metadataSparseWeight": 0.20,
            },
            "returnConfig": {
                "includeText": True,
                "includeScores": True,
                "includeProvenance": True,
            },
            "generation": {
                "temperature": 0.2,
                "maxTokens": 700,
            },
        }
        if filters:
            body["filters"] = filters
        payload = self._request("POST", f"/v1/corpora/{corpus_id}/search:generate", body=body)
        return _dict_payload(payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        base = self.base_url.rstrip("/")
        query = f"?{urlencode({k: v for k, v in (params or {}).items() if v is not None})}" if params else ""
        url = f"{base}{path}{query}"
        request_headers = {
            "accept": "application/json",
            "User-Agent": _BRANDING.api_user_agent,
            "X-API-Key": self.api_key,
        }
        data = None
        if body is not None:
            data = json.dumps(_camel_to_snake(body)).encode("utf-8")
            request_headers["content-type"] = "application/json"
        if headers:
            request_headers.update(headers)

        request = Request(url, data=data, method=method, headers=request_headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(5_000_000).decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            body_text = exc.read(1_000_000).decode("utf-8", errors="replace")
            raise K2ApiError(f"K2 API returned HTTP {exc.code}", status_code=exc.code, body=body_text) from exc
        except (URLError, TimeoutError) as exc:
            raise K2ApiError(f"K2 API connection failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise K2ApiError("K2 API returned invalid JSON.") from exc


def _list_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [item for item in payload[key] if isinstance(item, dict)]
    return []


def _dict_payload(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _camel_to_snake(value: Any) -> Any:
    if isinstance(value, list):
        return [_camel_to_snake(item) for item in value]
    if isinstance(value, dict):
        return {_to_snake(str(key)): _camel_to_snake(item) for key, item in value.items()}
    return value


def _to_snake(value: str) -> str:
    chars = []
    for index, char in enumerate(value):
        if char.isupper() and index:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)
