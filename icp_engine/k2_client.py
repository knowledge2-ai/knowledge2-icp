from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
            "User-Agent": "Knowledge2ICP/0.1",
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
