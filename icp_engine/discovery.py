from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

from .enrichment import normalize_domain
from .text import normalize_whitespace


SEARCH_TIMEOUT_SECONDS = 10
SERPER_BASE_URL = "https://google.serper.dev"
BLOCKED_RESULT_HOSTS = {
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "linkedin.com",
    "www.linkedin.com",
    "github.com",
    "www.github.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "www.facebook.com",
    "youtube.com",
    "www.youtube.com",
    "crunchbase.com",
    "www.crunchbase.com",
    "g2.com",
    "www.g2.com",
    "capterra.com",
    "www.capterra.com",
}

EXTERNAL_RESULT_HOSTS = {
    "github.com": "github",
    "linkedin.com": "linkedin",
    "x.com": "other",
    "twitter.com": "other",
    "facebook.com": "other",
    "youtube.com": "other",
    "instagram.com": "other",
    "crunchbase.com": "other",
    "g2.com": "other",
    "capterra.com": "other",
    "producthunt.com": "other",
}

EXTERNAL_REF_STOPWORDS = {
    "about",
    "company",
    "com",
    "github",
    "home",
    "inc",
    "io",
    "linkedin",
    "llc",
    "official",
    "profile",
    "the",
    "www",
}


@dataclass
class DiscoveryCandidate:
    company: str
    domain: str
    source_url: str
    source_title: str = ""
    notes: str = ""
    github_urls: list[str] = field(default_factory=list)
    linkedin_urls: list[str] = field(default_factory=list)
    other_urls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ExternalResultRef:
    bucket: str
    url: str
    title: str


def discover_companies(
    query: str,
    *,
    max_results: int = 10,
    fetcher: Callable[[str], str] | None = None,
) -> tuple[list[DiscoveryCandidate], list[str]]:
    if not query.strip():
        return [], ["Search query is empty."]

    provider = os.environ.get("ICP_SEARCH_PROVIDER", "").strip().lower()
    serper_key = os.environ.get("SERPER_API_KEY") or os.environ.get("SERP_API_KEY")
    warnings: list[str] = []
    if fetcher is None and serper_key and provider in {"", "serper", "serp"}:
        candidates, warnings = discover_companies_with_serper(query, max_results=max_results, api_key=serper_key)
        if candidates:
            return candidates, warnings
        warnings.append("Falling back to DuckDuckGo HTML search.")

    ddg_candidates, ddg_warnings = _duckduckgo_discovery(query, max_results=max_results, fetcher=fetcher)
    return ddg_candidates, [*warnings, *ddg_warnings]


def research_discovery(
    query: str,
    *,
    provider: str = "auto",
    max_results: int = 10,
    research_client: Any | None = None,
    search_fetcher: Callable[[str], str] | None = None,
    criteria_markdown: str = "",
) -> tuple[list[DiscoveryCandidate], list[str], str]:
    """Provider-aware company discovery with a graceful fallback cascade.

    Dispatches to the Perplexity research engine, the Serper SERP API, or the
    DuckDuckGo HTML path. ``auto`` mirrors today's cascade (Perplexity if a key
    or injected client is present, then Serper if keyed, then DuckDuckGo) so a
    set key "just works"; an explicit ``provider`` forces that engine first but
    still falls through to search on failure. Returns the candidates, accumulated
    warnings, and the provider that actually produced them (or ``"none"``).
    """
    if not query.strip():
        return [], ["Search query is empty."], "none"
    provider = (provider or "auto").strip().lower()
    if provider not in {"auto", "perplexity", "serper", "duckduckgo"}:
        provider = "auto"
    warnings: list[str] = []

    perplexity_enabled = provider == "perplexity" or (
        provider == "auto"
        and (research_client is not None or bool(os.environ.get("PERPLEXITY_API_KEY")))
    )
    if perplexity_enabled:
        candidates, perplexity_warnings = _perplexity_discovery(
            query, max_results=max_results, research_client=research_client, criteria_markdown=criteria_markdown
        )
        warnings.extend(perplexity_warnings)
        if candidates:
            return candidates, warnings, "perplexity"
        warnings.append("Falling back to search-provider discovery.")

    if provider == "duckduckgo":
        candidates, ddg_warnings = _duckduckgo_discovery(query, max_results=max_results, fetcher=search_fetcher)
        warnings.extend(ddg_warnings)
        return candidates, warnings, ("duckduckgo" if candidates else "none")

    serper_key = os.environ.get("SERPER_API_KEY") or os.environ.get("SERP_API_KEY")
    if provider in {"auto", "serper"} and search_fetcher is None and serper_key:
        candidates, serper_warnings = discover_companies_with_serper(
            query, max_results=max_results, api_key=serper_key
        )
        warnings.extend(serper_warnings)
        if candidates:
            return candidates, warnings, "serper"
        warnings.append("Falling back to DuckDuckGo HTML search.")

    candidates, ddg_warnings = _duckduckgo_discovery(query, max_results=max_results, fetcher=search_fetcher)
    warnings.extend(ddg_warnings)
    return candidates, warnings, ("duckduckgo" if candidates else "none")


def _perplexity_discovery(
    query: str,
    *,
    max_results: int,
    research_client: Any | None,
    criteria_markdown: str,
) -> tuple[list[DiscoveryCandidate], list[str]]:
    # Lazy import: perplexity.py imports DiscoveryCandidate from this module, so a
    # top-level import would form a cycle.
    from .perplexity import PerplexityUnavailable, research_companies

    try:
        return research_companies(
            query, max_results=max_results, criteria_markdown=criteria_markdown, client=research_client
        )
    except PerplexityUnavailable as exc:
        return [], [f"Perplexity research provider unavailable: {exc}"]


def _duckduckgo_discovery(
    query: str,
    *,
    max_results: int,
    fetcher: Callable[[str], str] | None,
) -> tuple[list[DiscoveryCandidate], list[str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    fetch = fetcher or _fetch_url
    try:
        body = fetch(url)
    except Exception as exc:
        return [], [f"Search provider failed: {exc}"]

    links = extract_search_links(body)
    candidates = candidates_from_links(links, max_results=max_results)
    warnings = [] if candidates else ["No company domains were discovered from search results."]
    return candidates, warnings


def discover_companies_with_serper(
    query: str,
    *,
    max_results: int = 10,
    api_key: str | None = None,
    fetcher: Callable[[str, bytes, dict[str, str]], str] | None = None,
) -> tuple[list[DiscoveryCandidate], list[str]]:
    key = api_key or os.environ.get("SERPER_API_KEY") or os.environ.get("SERP_API_KEY")
    if not key:
        return [], ["SERPER_API_KEY or SERP_API_KEY is not configured."]
    payload = json.dumps({"q": query, "num": max(10, min(max_results * 2, 100))}).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Knowledge2ICPDiscovery/0.1 (+https://knowledge2.ai)",
        "X-API-KEY": key,
    }
    try:
        body = (fetcher or _post_json_text)(f"{SERPER_BASE_URL}/search", payload, headers)
        data = json.loads(body)
    except Exception as exc:
        return [], [f"Serper search provider failed: {exc}"]
    candidates = candidates_from_serper_payload(data, max_results=max_results)
    warnings = [] if candidates else ["No company domains were discovered from Serper results."]
    return candidates, warnings


def discover_companies_from_url(
    url: str,
    *,
    max_results: int = 25,
    fetcher: Callable[[str], str] | None = None,
) -> tuple[list[DiscoveryCandidate], list[str]]:
    if not url.strip():
        return [], ["Portfolio/source URL is empty."]
    fetch = fetcher or _fetch_url
    try:
        body = fetch(url)
    except Exception as exc:
        return [], [f"Source page fetch failed: {exc}"]
    links = extract_page_links(body, base_url=url)
    candidates = candidates_from_links(links, max_results=max_results)
    warnings = [] if candidates else ["No company domains were discovered from source page links."]
    return candidates, warnings


def candidates_from_serper_payload(payload: dict[str, object], *, max_results: int = 10) -> list[DiscoveryCandidate]:
    organic = payload.get("organic")
    items = organic if isinstance(organic, list) else []
    links = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "")
        title = str(item.get("title") or "")
        snippet = str(item.get("snippet") or "")
        links.append((link, title or snippet))
    return candidates_from_links(links, max_results=max_results)


def extract_search_links(body: str) -> list[tuple[str, str]]:
    parser = _SearchLinkParser()
    parser.feed(body)
    return parser.links


def extract_page_links(body: str, *, base_url: str = "") -> list[tuple[str, str]]:
    parser = _AnchorLinkParser(base_url)
    parser.feed(body)
    return parser.links


def candidates_from_links(links: list[tuple[str, str]], *, max_results: int = 10) -> list[DiscoveryCandidate]:
    by_domain: dict[str, DiscoveryCandidate] = {}
    external_refs: list[_ExternalResultRef] = []

    for raw_url, raw_title in links:
        url = _unwrap_duckduckgo_url(raw_url)
        title = normalize_whitespace(html.unescape(raw_title))
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        if not host:
            continue
        external_bucket = _external_ref_bucket(host)
        if external_bucket:
            external_refs.append(_ExternalResultRef(external_bucket, url, title))
            continue
        if host in {item.removeprefix("www.") for item in BLOCKED_RESULT_HOSTS}:
            continue
        domain = normalize_domain(host)
        if not domain or "." not in domain:
            continue
        if domain not in by_domain and len(by_domain) < max_results:
            by_domain[domain] = DiscoveryCandidate(
                company=_company_name_from_title_or_domain(title, domain),
                domain=domain,
                source_url=url,
                source_title=title,
                notes=f"Discovered from search result: {title}" if title else "Discovered from search result.",
            )

    for candidate in by_domain.values():
        _attach_external_refs(candidate, external_refs)
    return list(by_domain.values())


def parse_seed_companies(seed_text: str) -> list[DiscoveryCandidate]:
    candidates: list[DiscoveryCandidate] = []
    for line in seed_text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        parts = [part.strip() for part in re.split(r"[,|\t]", cleaned) if part.strip()]
        if _looks_like_seed_header(parts):
            continue
        if len(parts) == 1:
            domain = normalize_domain(parts[0])
            company = _company_name_from_title_or_domain("", domain)
        else:
            company = parts[0]
            domain = normalize_domain(parts[1])
        if domain:
            candidates.append(
                DiscoveryCandidate(
                    company=company or _company_name_from_title_or_domain("", domain),
                    domain=domain,
                    source_url=f"https://{domain}",
                    source_title="Manual seed",
                    notes="Manually seeded by operator.",
                )
            )
    return candidates


def _looks_like_seed_header(parts: list[str]) -> bool:
    if len(parts) < 2:
        return False
    first = parts[0].strip().lower()
    second = parts[1].strip().lower()
    return first in {"company", "company name", "name", "account"} and second in {"domain", "website", "url", "company domain"}


def _fetch_url(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Knowledge2ICPDiscovery/0.1 (+https://knowledge2.ai)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=SEARCH_TIMEOUT_SECONDS) as response:
        return response.read(1_500_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def _post_json_text(url: str, payload: bytes, headers: dict[str, str]) -> str:
    request = Request(url, data=payload, method="POST", headers=headers)
    with urlopen(request, timeout=SEARCH_TIMEOUT_SECONDS) as response:
        return response.read(1_500_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def _unwrap_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    if (not parsed.netloc or "duckduckgo.com" in parsed.netloc) and parsed.path.startswith("/l/"):
        values = parse_qs(parsed.query).get("uddg")
        if values:
            return values[0]
    return url


def _company_name_from_title_or_domain(title: str, domain: str) -> str:
    if title:
        first = re.split(r"[-|:]", title, maxsplit=1)[0].strip()
        first = re.sub(r"\b(official site|homepage|software|platform)\b", "", first, flags=re.I).strip()
        if first and len(first) <= 80:
            return first
    stem = domain.removeprefix("www.").split(".", 1)[0]
    return " ".join(part.capitalize() for part in re.split(r"[-_]", stem) if part)


def _external_ref_bucket(host: str) -> str:
    clean_host = host.removeprefix("www.")
    for external_host, bucket in EXTERNAL_RESULT_HOSTS.items():
        if clean_host == external_host or clean_host.endswith(f".{external_host}"):
            return bucket
    return ""


def _attach_external_refs(candidate: DiscoveryCandidate, refs: list[_ExternalResultRef]) -> None:
    for ref in refs:
        if not _external_ref_matches_candidate(ref, candidate):
            continue
        if ref.bucket == "github":
            _append_unique(candidate.github_urls, ref.url)
        elif ref.bucket == "linkedin":
            _append_unique(candidate.linkedin_urls, ref.url)
        else:
            _append_unique(candidate.other_urls, ref.url)


def _external_ref_matches_candidate(ref: _ExternalResultRef, candidate: DiscoveryCandidate) -> bool:
    candidate_terms = _company_terms(candidate.company) | _domain_terms(candidate.domain)
    ref_terms = _company_terms(ref.title) | _company_terms(urlparse(ref.url).path)
    return bool(candidate_terms and ref_terms and candidate_terms.intersection(ref_terms))


def _company_terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 1 and term not in EXTERNAL_REF_STOPWORDS}


def _domain_terms(domain: str) -> set[str]:
    host = normalize_domain(domain).split(":", 1)[0]
    parts = host.removeprefix("www.").split(".")
    return {part for part in parts[:-1] if len(part) > 1 and part not in EXTERNAL_REF_STOPWORDS}


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


class _SearchLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = {key: value or "" for key, value in attrs}
        href = attr_map.get("href", "")
        class_name = attr_map.get("class", "")
        if href and ("result__a" in class_name or "/l/?" in href or href.startswith("http")):
            self._current_href = href
            self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href:
            title = normalize_whitespace(" ".join(self._current_text))
            self.links.append((self._current_href, title))
            self._current_href = None
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)


class _AnchorLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._current_href = ""
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href") or ""
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            return
        self._current_href = urljoin(self.base_url, href)
        self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href:
            text = normalize_whitespace(" ".join(self._current_text))
            self.links.append((self._current_href, text))
            self._current_href = ""
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)
