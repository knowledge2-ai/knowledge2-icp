from __future__ import annotations

import json
import os
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .tenant import Branding


_BRANDING = Branding()


def search_github_metadata(company: str, domain: str, *, max_repos: int = 3, timeout_seconds: float = 6.0) -> dict[str, object]:
    query = quote_plus(f'"{company}" OR "{domain}"')
    url = f"https://api.github.com/search/repositories?q={query}&per_page={max_repos}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _BRANDING.api_user_agent,
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
    except Exception as exc:
        return {
            "status": "warning",
            "warning": f"GitHub metadata search failed: {exc}",
            "repositories": [],
        }

    repos = []
    for item in payload.get("items", [])[:max_repos]:
        repos.append(
            {
                "name": item.get("full_name"),
                "url": item.get("html_url"),
                "description": item.get("description") or "",
                "stars": item.get("stargazers_count") or 0,
                "language": item.get("language") or "",
                "updated_at": item.get("updated_at"),
            }
        )
    return {
        "status": "ok",
        "repositories": repos,
    }

