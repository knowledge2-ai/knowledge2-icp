from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


APOLLO_BASE_URL = "https://api.apollo.io/api/v1"
DEFAULT_PERSONA_TITLES = [
    "chief product officer",
    "vp product",
    "head of product",
    "chief technology officer",
    "vp engineering",
    "chief data officer",
    "vp strategy",
]


@dataclass(frozen=True)
class ApolloClient:
    api_key: str | None = None
    base_url: str = APOLLO_BASE_URL
    timeout_seconds: float = 12.0

    @classmethod
    def from_env(cls) -> "ApolloClient":
        return cls(api_key=os.environ.get("APOLLO_API_KEY"))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search_organizations(self, *, domains: list[str], query: str = "", per_page: int = 5) -> dict[str, object]:
        if not self.configured:
            return {"status": "skipped", "reason": "APOLLO_API_KEY is not configured.", "organizations": []}
        params: list[tuple[str, str | int]] = [("per_page", max(1, min(per_page, 100)))]
        for domain in domains:
            params.append(("q_organization_domains_list[]", domain))
        if query:
            params.append(("q_keywords", query))
        payload = self._post_query("/mixed_companies/search", params)
        return {
            "status": "ok",
            "organizations": _compact_organizations(payload),
        }

    def search_people(self, *, domain: str, titles: list[str] | None = None, per_page: int = 8) -> dict[str, object]:
        if not self.configured:
            return {"status": "skipped", "reason": "APOLLO_API_KEY is not configured.", "people": []}
        params: list[tuple[str, str | int | bool]] = [
            ("per_page", max(1, min(per_page, 100))),
            ("q_organization_domains_list[]", domain),
            ("include_similar_titles", "true"),
        ]
        for title in titles or DEFAULT_PERSONA_TITLES:
            params.append(("person_titles[]", title))
        payload = self._post_query("/mixed_people/api_search", params)
        return {
            "status": "ok",
            "people": _compact_people(payload),
        }

    def _post_query(self, path: str, params: list[tuple[str, str | int | bool]]) -> dict[str, object]:
        url = f"{self.base_url.rstrip('/')}{path}?{urlencode(params)}"
        request = Request(
            url,
            data=b"{}",
            method="POST",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "cache-control": "no-cache",
                "x-api-key": self.api_key or "",
                "User-Agent": "Knowledge2ICP/0.1",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read(2_000_000).decode("utf-8", errors="replace"))


def _compact_organizations(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_items = payload.get("organizations") or payload.get("accounts") or []
    items = raw_items if isinstance(raw_items, list) else []
    result = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "website_url": item.get("website_url"),
                "linkedin_url": item.get("linkedin_url"),
                "industry": item.get("industry"),
                "estimated_num_employees": item.get("estimated_num_employees"),
                "city": item.get("city"),
                "state": item.get("state"),
                "country": item.get("country"),
            }
        )
    return result


def _compact_people(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_items = payload.get("people") or payload.get("contacts") or []
    items = raw_items if isinstance(raw_items, list) else []
    result = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        org = item.get("organization") if isinstance(item.get("organization"), dict) else {}
        result.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "title": item.get("title"),
                "email": item.get("email"),
                "email_status": item.get("email_status"),
                "linkedin_url": item.get("linkedin_url"),
                "city": item.get("city"),
                "state": item.get("state"),
                "country": item.get("country"),
                "photo_url": item.get("photo_url"),
                "organization": {
                    "id": org.get("id"),
                    "name": org.get("name"),
                    "website_url": org.get("website_url"),
                    "linkedin_url": org.get("linkedin_url"),
                },
            }
        )
    return result
