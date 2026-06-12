from __future__ import annotations

import hashlib
import json
import socket
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import CompanyInput, Evidence
from .text import compact_snippet, html_to_text


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
    return parsed.netloc or parsed.path


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
) -> tuple[list[Evidence], list[str]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    evidence: list[Evidence] = []
    warnings: list[str] = []
    first_homepage_error: str | None = None

    for url in candidate_urls(company.domain):
        if len(evidence) >= max_pages:
            break
        try:
            item = _fetch_or_read_cache(url, cache_dir, timeout_seconds)
        except (HTTPError, URLError, TimeoutError, socket.timeout, ssl.SSLError, ValueError) as exc:
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
            )
        )

    if not evidence:
        if first_homepage_error:
            warnings.append(f"Could not fetch homepage: {first_homepage_error}")
        warnings.append("No public domain evidence fetched; scoring uses CSV fields and notes only.")
    return evidence, warnings


def _fetch_or_read_cache(url: str, cache_dir: Path, timeout_seconds: float) -> dict[str, str]:
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
        title, text = html_to_text(body) if "html" in content_type else ("", body)

    item = {"url": url, "title": title, "text": compact_snippet(text, 5000)}
    cache_path.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")
    return item
