from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .evidence import dedupe_evidence, is_high_value_url
from .models import CompanyInput, Evidence
from .text import compact_snippet, html_to_text_and_links


DEFAULT_PATHS = [
    "",
    "about",
    "company",
    "product",
    "products",
    "platform",
    "solutions",
    "customers",
    "case-studies",
    "pricing",
    "docs",
    "developers",
    "api",
    "integrations",
    "blog",
    "news",
    "press",
    "changelog",
    "ai",
    "copilot",
]


def normalize_domain(domain: str) -> str:
    domain = domain.strip()
    if not domain:
        return ""
    parsed = urlparse(domain if "://" in domain else f"https://{domain}")
    host = (parsed.hostname or parsed.path.split("/", 1)[0]).lower()
    if not host:
        return ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port and ":" not in host:
        return f"{host}:{port}"
    return host


def candidate_urls(domain: str, paths: list[str] | None = None) -> list[str]:
    clean_domain = normalize_domain(domain)
    paths = DEFAULT_PATHS if paths is None else paths
    domains = [clean_domain]
    if clean_domain and not clean_domain.startswith("www."):
        domains.append(f"www.{clean_domain}")

    urls: list[str] = []
    for path in paths:
        suffix = f"/{path.strip('/')}" if path else ""
        for candidate_domain in domains:
            urls.append(f"https://{candidate_domain}{suffix}")
    return urls


def fetch_company_evidence(
    company: CompanyInput,
    cache_dir: Path,
    *,
    timeout_seconds: float = 8.0,
    max_pages: int = 10,
    extra_urls: list[str] | None = None,
    max_attempts: int | None = None,
    max_failures: int | None = None,
) -> tuple[list[Evidence], list[str]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    evidence: list[Evidence] = []
    warnings: list[str] = []
    first_homepage_error: str | None = None
    attempts = 0
    failures = 0
    max_attempts = max_attempts or max(8, max_pages * 3)
    max_failures = max_failures or max(6, max_pages * 2)

    urls = _prioritized_fetch_urls(company.domain, extra_urls or [])
    seen_urls: set[str] = set()
    skip_warnings: set[str] = set()
    index = 0
    while index < len(urls):
        url = urls[index]
        index += 1
        normalized_url = _normalized_url_key(url)
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        skip_reason = _resource_skip_reason(url)
        if skip_reason:
            skip_warnings.add(skip_reason)
            continue
        if not _is_public_fetch_url(url):
            continue
        if len(evidence) >= max_pages or attempts >= max_attempts or failures >= max_failures:
            break
        attempts += 1
        try:
            item = _fetch_or_read_cache(url, cache_dir, timeout_seconds)
        except (HTTPError, URLError, TimeoutError, socket.timeout, ssl.SSLError, ValueError) as exc:
            failures += 1
            if not evidence and url.rstrip("/") == f"https://{normalize_domain(company.domain)}":
                first_homepage_error = str(exc)
            continue
        if not item["text"]:
            continue
        evidence.append(
            Evidence(
                evidence_id=f"e{len(evidence) + 1}",
                url=item["url"],
                title=item.get("title", ""),
                text=item["text"],
                source_type=_source_type(item["url"]),
                metadata=_evidence_metadata(item),
            )
        )
        for link in _interesting_links(item.get("links", []), company.domain):
            if _normalized_url_key(link) not in seen_urls:
                urls.append(link)

    evidence = dedupe_evidence(evidence)
    warnings.extend(sorted(skip_warnings))

    if not evidence:
        if first_homepage_error:
            warnings.append(f"Could not fetch homepage: {first_homepage_error}")
        warnings.append("No public domain evidence fetched; scoring uses CSV fields and notes only.")
    if attempts >= max_attempts:
        warnings.append(f"Fetch attempt cap reached at {max_attempts} attempts.")
    if failures >= max_failures:
        warnings.append(f"Fetch failure cap reached at {max_failures} failures.")
    return evidence, warnings


def _fetch_or_read_cache(url: str, cache_dir: Path, timeout_seconds: float) -> dict[str, str]:
    if not _is_public_fetch_url(url):
        raise ValueError("Refusing to fetch non-public URL.")
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    request = Request(
        url,
        headers={
            "User-Agent": "Knowledge2ICP/0.1 (+https://knowledge2.ai)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise ValueError(f"Unsupported content type {content_type}")
        raw = response.read(1_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
        body = raw.decode(charset, errors="replace")
        if "html" in content_type:
            title, text, links = html_to_text_and_links(body, url)
        else:
            title, text, links = "", body, []

    item = {"url": url, "title": title, "text": compact_snippet(text, 5000), "links": links}
    cache_path.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")
    return item


def _evidence_metadata(item: dict[str, object]) -> dict[str, object]:
    url = str(item.get("url", ""))
    links = [str(link) for link in item.get("links", []) if isinstance(link, str)]
    return {
        "source_type": _source_type(url),
        "page_category": _page_category(url),
        "links": links[:80],
        "external_links": _external_links(url, links)[:40],
    }


def _prioritized_fetch_urls(domain: str, extra_urls: list[str]) -> list[str]:
    website_urls = candidate_urls(domain)
    resource_urls = _public_resource_urls(extra_urls)
    if not resource_urls:
        return website_urls
    return website_urls[:2] + resource_urls + website_urls[2:]


def _public_resource_urls(urls: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_url in urls:
        parsed = urlparse(str(raw_url).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        normalized = str(raw_url).split("#", 1)[0].strip()
        key = _normalized_url_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result[:12]


def _resource_skip_reason(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "LinkedIn URLs were recorded as public refs but not fetched; authenticated LinkedIn scraping is intentionally unsupported."
    return ""


def _source_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "github.com" in host:
        return "github"
    if "linkedin.com" in host:
        return "linkedin"
    if any(name in host for name in ["twitter.com", "x.com", "facebook.com", "youtube.com", "instagram.com", "tiktok.com"]):
        return "social"
    if any(name in host for name in ["crunchbase.com", "g2.com", "capterra.com", "producthunt.com"]):
        return "marketplace"
    return "website"


def _page_category(url: str) -> str:
    if _source_type(url) in {"github", "linkedin", "social", "marketplace"}:
        return "profile"
    path = urlparse(url).path.lower()
    categories = {
        "docs": ["docs", "documentation", "developer", "developers", "api"],
        "pricing": ["pricing", "plans", "packages"],
        "customers": ["customers", "case-studies", "case-study", "stories"],
        "product": ["product", "platform", "solutions", "features"],
        "ai": ["ai", "copilot", "assistant", "gpt"],
        "company": ["about", "company", "press", "news"],
        "careers": ["careers", "jobs"],
        "contact": ["contact", "demo", "sales"],
    }
    for category, terms in categories.items():
        if any(term in path for term in terms):
            return category
    return "homepage" if path in {"", "/"} else "other"


def _external_links(source_url: str, links: list[str]) -> list[str]:
    source_host = urlparse(source_url).netloc.lower().removeprefix("www.")
    result = []
    seen = set()
    for link in links:
        parsed = urlparse(link)
        host = parsed.netloc.lower().removeprefix("www.")
        if not host or host == source_host:
            continue
        normalized = link.split("#", 1)[0]
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _interesting_links(links: list[str], domain: str) -> list[str]:
    clean_domain = normalize_domain(domain)
    candidates = []
    for link in links:
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"}:
            continue
        if not _is_public_fetch_url(link):
            continue
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host != clean_domain.removeprefix("www."):
            continue
        if is_high_value_url(link):
            candidates.append(link.split("#", 1)[0])
    return candidates[:20]


def _is_public_fetch_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.hostname
    if not host or host.lower() == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        pass
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    public_addresses = []
    for address in addresses:
        ip_text = address[4][0]
        try:
            public_addresses.append(ipaddress.ip_address(ip_text).is_global)
        except ValueError:
            return False
    return bool(public_addresses) and all(public_addresses)


def _normalized_url_key(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/").lower()
    return f"{host}{path}"
