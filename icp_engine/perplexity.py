from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .discovery import DiscoveryCandidate
from .enrichment import normalize_domain
from .tenant import Branding


_BRANDING = Branding()

DEFAULT_MODEL = "sonar"
DEFAULT_BASE_URL = "https://api.perplexity.ai"

# Structured output schema. Perplexity Sonar returns the JSON as a string in
# choices[0].message.content; we parse it into DiscoveryCandidates so discovery,
# the Claude judge, and K2 all speak the same "company + citations" language.
COMPANIES_SCHEMA = {
    "type": "object",
    "required": ["companies"],
    "properties": {
        "companies": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["company", "domain"],
                "properties": {
                    "company": {"type": "string"},
                    "domain": {"type": "string", "description": "Bare primary website domain, e.g. acme.com."},
                    "reason": {"type": "string", "description": "One sentence on why the company fits the ICP."},
                },
            },
        }
    },
}


class PerplexityApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class PerplexityUnavailable(RuntimeError):
    pass


def research_companies(
    brief: str,
    *,
    max_results: int = 10,
    criteria_markdown: str = "",
    config: dict[str, Any] | None = None,
    client: Any | None = None,
) -> tuple[list[DiscoveryCandidate], list[str]]:
    """Source ICP-fit companies from the live web with Perplexity Sonar.

    Takes a natural-language brief, asks Sonar for a structured company list
    grounded in web citations, and maps it into ``DiscoveryCandidate``s. The ICP
    framing comes from the versioned ``criteria_markdown`` (not a hardcoded block)
    so tenancy stays config-driven. Raises ``PerplexityUnavailable`` when
    ``PERPLEXITY_API_KEY`` is missing so callers can fall back to other providers.
    """
    if not brief.strip():
        return [], ["Research brief is empty."]
    settings = config or {}
    model = str(settings.get("model") or os.environ.get("ICP_PERPLEXITY_MODEL", DEFAULT_MODEL))
    max_tokens = int(settings.get("max_tokens") or _int_env("ICP_PERPLEXITY_MAX_TOKENS", 1024))
    system_prompt = _system_prompt(criteria_markdown)
    user_prompt = _research_prompt(brief, max_results)
    _write_prompt_debug(brief, f"{system_prompt}\n\n{user_prompt}")

    active = client or _default_client()
    try:
        response = active.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_schema", "json_schema": {"schema": COMPANIES_SCHEMA}},
        )
    except PerplexityApiError as exc:
        return [], [f"Perplexity research provider failed: {exc}"]
    return _candidates_from_response(response, max_results=max_results)


@dataclass(frozen=True)
class PerplexityRestClient:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("Perplexity API key is required for research discovery.")

    def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format is not None:
            body["response_format"] = response_format
        payload = self._request("POST", "/chat/completions", body=body)
        return payload if isinstance(payload, dict) else {}

    def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": _BRANDING.discovery_user_agent,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(5_000_000).decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            body_text = exc.read(1_000_000).decode("utf-8", errors="replace")
            raise PerplexityApiError(
                f"Perplexity API returned HTTP {exc.code}", status_code=exc.code, body=body_text
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise PerplexityApiError(f"Perplexity API connection failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PerplexityApiError("Perplexity API returned invalid JSON.") from exc


def _default_client() -> PerplexityRestClient:
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise PerplexityUnavailable("Set PERPLEXITY_API_KEY to enable Perplexity research discovery.")
    base_url = os.environ.get("PERPLEXITY_BASE_URL", DEFAULT_BASE_URL)
    return PerplexityRestClient(api_key=api_key, base_url=base_url)


def _candidates_from_response(
    response: Any, *, max_results: int
) -> tuple[list[DiscoveryCandidate], list[str]]:
    content, citations = _extract_content_and_citations(response)
    if not content.strip():
        return [], ["Perplexity returned no research content."]
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return [], ["Perplexity returned non-JSON research content."]
    companies = data.get("companies") if isinstance(data, dict) else None
    if not isinstance(companies, list):
        return [], ["Perplexity research payload had no companies array."]

    candidates: list[DiscoveryCandidate] = []
    seen: set[str] = set()
    for item in companies:
        if not isinstance(item, dict):
            continue
        domain = normalize_domain(str(item.get("domain") or ""))
        if not domain or domain in seen:
            continue
        seen.add(domain)
        name = str(item.get("company") or "").strip() or domain
        reason = str(item.get("reason") or "").strip()
        matching = [url for url in citations if domain in url.lower()]
        candidates.append(
            DiscoveryCandidate(
                company=name,
                domain=domain,
                source_url=matching[0] if matching else f"https://{domain}",
                source_title="Perplexity research result",
                notes=reason or "Sourced via Perplexity research.",
                other_urls=matching,
            )
        )
        if len(candidates) >= max_results:
            break

    warnings = [] if candidates else ["No company domains were discovered from Perplexity research."]
    return candidates, warnings


def _extract_content_and_citations(response: Any) -> tuple[str, list[str]]:
    if not isinstance(response, dict):
        return "", []
    content = ""
    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = str(message.get("content") or "")
    citations = response.get("citations")
    urls = [str(item) for item in citations if isinstance(item, str)] if isinstance(citations, list) else []
    if not urls and isinstance(response.get("search_results"), list):
        urls = [
            str(result.get("url"))
            for result in response["search_results"]
            if isinstance(result, dict) and result.get("url")
        ]
    return content, urls


# A full analyst ICP rubric runs ~17KB and embeds internal methodology — hard
# gates, scoring math, TAM models, exclusion definitions. Handed wholesale to
# Sonar as "authoritative criteria," the model applies the gating itself and
# returns an empty companies array (observed: >=8KB rubric -> 0 results, while
# the same brief with <=4KB returns a full list). Discovery only needs the
# decision-relevant head of the doc (the "bottom line" + hard gates), so we cap
# the injected rubric. The downstream qualifier still scores against the full
# criteria; this bound only governs what we ask the web-research model to source.
_DISCOVERY_CRITERIA_CHAR_BUDGET = 4000


def _bounded_rubric(criteria_markdown: str) -> str:
    rubric = criteria_markdown.strip()
    if len(rubric) <= _DISCOVERY_CRITERIA_CHAR_BUDGET:
        return rubric
    head = rubric[:_DISCOVERY_CRITERIA_CHAR_BUDGET]
    # Cut back to the last paragraph break so we don't truncate mid-sentence.
    cut = head.rfind("\n\n")
    if cut > _DISCOVERY_CRITERIA_CHAR_BUDGET // 2:
        head = head[:cut]
    return f"{head.rstrip()}\n\n(Criteria truncated for sourcing; full rubric applied downstream.)"


def _system_prompt(criteria_markdown: str) -> str:
    rubric = _bounded_rubric(criteria_markdown) or "(no criteria provided)"
    return f"""You are a B2B GTM research analyst sourcing companies for a lead-generation funnel.
Find real, currently-operating companies that fit the ICP criteria below using live web research.

ICP CRITERIA (authoritative, versioned):
{rubric}

For each company return its primary website domain (bare domain, e.g. acme.com) and a one-sentence
reason it fits. Only include companies you can support with web sources; do not invent companies or
domains. Respond by calling the structured json_schema with a `companies` array."""


def _research_prompt(brief: str, max_results: int) -> str:
    return (
        f"Research brief: {brief.strip()}\n\n"
        f"Return up to {max_results} distinct companies that best match the brief and the ICP criteria."
    )


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _write_prompt_debug(brief: str, prompt: str) -> None:
    debug_dir = os.environ.get("ICP_DEBUG_PROMPT_DIR")
    if not debug_dir:
        return
    from pathlib import Path

    safe_name = "".join(char.lower() if char.isalnum() else "-" for char in brief[:60]).strip("-")
    path = Path(debug_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{safe_name or 'brief'}.perplexity.prompt.txt").write_text(prompt, encoding="utf-8")
