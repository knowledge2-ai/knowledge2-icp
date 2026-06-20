from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .tenant import Branding


_BRANDING = Branding()

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
        people = _compact_people(payload)
        enriched = self._bulk_match_people(people)
        return {
            "status": "ok",
            "people": _merge_people(people, enriched) if enriched else people,
        }

    def _bulk_match_people(self, people: list[dict[str, object]]) -> list[dict[str, object]]:
        details = [{"id": person["id"]} for person in people if person.get("id")][:10]
        if not details:
            return []
        # Reveal the real personal email — this is the point of People Match and
        # spends one credit per matched contact. Phones stay off (unused).
        params: list[tuple[str, str | int | bool]] = [
            ("reveal_personal_emails", "true"),
            ("reveal_phone_number", "false"),
        ]
        try:
            payload = self._post_query("/people/bulk_match", params, body={"details": details})
        except (OSError, ValueError):
            return []
        matches = payload.get("matches")
        return _compact_people({"people": matches if isinstance(matches, list) else []})

    def _post_query(
        self,
        path: str,
        params: list[tuple[str, str | int | bool]],
        *,
        body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        url = f"{self.base_url.rstrip('/')}{path}?{urlencode(params)}"
        data = json.dumps(body).encode("utf-8") if body is not None else b"{}"
        request = Request(
            url,
            data=data,
            method="POST",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "cache-control": "no-cache",
                "x-api-key": self.api_key or "",
                "User-Agent": _BRANDING.api_user_agent,
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


def _merge_people(search_people: list[dict[str, object]], enriched: list[dict[str, object]]) -> list[dict[str, object]]:
    enriched_by_id = {person.get("id"): person for person in enriched if person.get("id")}
    return [{**person, **enriched_by_id.get(person.get("id"), {})} for person in search_people]


# Email availability for a person record: a revealed record carries a real email
# (-> "verified" unless Apollo already labeled it); the search teaser only has
# has_email, surfaced as "available_unrevealed" so a slot reads honestly rather
# than looking verified.
def _email_status(item: dict[str, object], contact: dict[str, object]) -> str:
    email = item.get("email") or contact.get("email") or ""
    if email and "email_not_unlocked" not in str(email):
        return str(item.get("email_status") or contact.get("email_status") or "verified")
    if item.get("email_status") or contact.get("email_status"):
        return str(item.get("email_status") or contact.get("email_status"))
    if item.get("has_email") or contact.get("has_email"):
        return "available_unrevealed"
    return ""


def _compact_people(payload: dict[str, object]) -> list[dict[str, object]]:
    raw_items = payload.get("people") or payload.get("contacts") or []
    items = raw_items if isinstance(raw_items, list) else []
    result = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        org = item.get("organization") if isinstance(item.get("organization"), dict) else {}
        contact = item.get("contact") if isinstance(item.get("contact"), dict) else {}
        email = item.get("email") or contact.get("email") or ""
        # Apollo returns a locked "email_not_unlocked@domain" placeholder until a
        # reveal credit is spent — never surface it as a real address.
        if "email_not_unlocked" in str(email):
            email = ""
        result.append(
            {
                "id": item.get("id"),
                "name": item.get("name") or contact.get("name"),
                "title": item.get("title") or contact.get("title"),
                "email": email,
                "email_status": _email_status(item, contact),
                "revealed": bool(email),
                "linkedin_url": item.get("linkedin_url") or contact.get("linkedin_url"),
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
