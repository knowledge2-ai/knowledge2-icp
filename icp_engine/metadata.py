from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import CompanyInput, Evidence
from .text import keyword_hits


SIGNAL_GROUPS = {
    "ai": ["ai", "artificial intelligence", "generative ai", "copilot", "assistant", "gpt", "llm"],
    "workflow": ["workflow", "dispatch", "claims", "tickets", "records", "work orders", "approvals"],
    "data": ["analytics", "reporting", "telematics", "diagnostics", "transactions", "documents"],
    "integration": ["api", "developer", "docs", "integration", "webhook", "sso", "permissions"],
    "commercial": ["customers", "case study", "trusted by", "pricing", "demo", "enterprise"],
}

REF_PATTERNS = {
    "github_urls": ["github.com"],
    "linkedin_urls": ["linkedin.com/company", "linkedin.com/in"],
    "social_urls": ["twitter.com", "x.com/", "facebook.com", "youtube.com", "instagram.com", "tiktok.com"],
    "marketplace_urls": ["crunchbase.com", "g2.com", "capterra.com", "producthunt.com"],
    "docs_urls": ["docs.", "/docs", "/developers", "/developer", "/api"],
    "pricing_urls": ["/pricing", "/plans"],
    "careers_urls": ["/careers", "/jobs"],
    "contact_urls": ["/contact", "/demo", "/sales"],
    "other_urls": [],
}


def classify_source(url: str, metadata: dict[str, object] | None = None) -> dict[str, str]:
    metadata = metadata or {}
    source_type = str(metadata.get("source_type") or _source_type(url))
    page_category = str(metadata.get("page_category") or _page_category(url))
    return {"source_type": source_type, "page_category": page_category}


def enrich_evidence_metadata(evidence: list[Evidence]) -> list[dict[str, object]]:
    enriched = []
    for item in evidence:
        classification = classify_source(item.url, item.metadata)
        signal_tags = _signal_tags(item.text, item.url)
        enriched.append(
            {
                "evidence_id": item.evidence_id,
                "url": item.url,
                "title": item.title,
                "source_type": classification["source_type"],
                "page_category": classification["page_category"],
                "signal_tags": signal_tags,
                "link_count": len(_metadata_links(item)),
                "external_link_count": len(_metadata_external_links(item)),
            }
        )
    return enriched


def lead_metadata_summary(company: CompanyInput, evidence: list[Evidence], candidate_refs: dict[str, object] | None = None) -> dict[str, object]:
    candidate_refs = candidate_refs or {}
    evidence_metadata = enrich_evidence_metadata(evidence)
    refs = _public_refs(evidence, candidate_refs)
    emails = _public_emails(evidence)
    source_counts = _source_counts(evidence_metadata)
    signal_tags = sorted({tag for item in evidence_metadata for tag in item.get("signal_tags", [])})
    intelligence_coverage = _intelligence_coverage(refs, evidence_metadata)
    return {
        "company": company.company,
        "domain": company.domain,
        "source_counts": source_counts,
        "source_refs": refs,
        "public_emails": emails,
        "signal_tags": signal_tags,
        "public_profile_count": sum(len(refs.get(key, [])) for key in ["github_urls", "linkedin_urls", "social_urls"]),
        "public_resource_count": sum(len(refs.get(key, [])) for key in ["docs_urls", "pricing_urls", "marketplace_urls", "careers_urls", "contact_urls", "other_urls"]),
        "intelligence_coverage": intelligence_coverage,
        "evidence_metadata": evidence_metadata,
        "k2_metadata_preview": {
            "domain": company.domain,
            "company": company.company,
            "source_count": len(evidence),
            "source_types": sorted(source_counts.keys()),
            "signal_tags": signal_tags,
        },
    }


def refs_from_candidate(candidate: object) -> dict[str, object]:
    return {
        "github_urls": list(getattr(candidate, "github_urls", []) or []),
        "linkedin_urls": list(getattr(candidate, "linkedin_urls", []) or []),
        "other_urls": list(getattr(candidate, "other_urls", []) or []),
        "source_url": getattr(candidate, "source_url", ""),
    }


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
    if path in {"", "/"}:
        return "homepage"
    if any(term in path for term in ["/docs", "/developers", "/api"]):
        return "docs"
    if "pricing" in path or "plans" in path:
        return "pricing"
    if "case" in path or "customers" in path:
        return "customers"
    if "careers" in path or "jobs" in path:
        return "careers"
    if "contact" in path or "demo" in path or "sales" in path:
        return "contact"
    if any(term in path for term in ["ai", "copilot", "assistant", "gpt"]):
        return "ai"
    if any(term in path for term in ["product", "platform", "solutions", "features"]):
        return "product"
    return "other"


def _signal_tags(text: str, url: str) -> list[str]:
    haystack = f"{url} {text}".lower()
    return [group for group, terms in SIGNAL_GROUPS.items() if keyword_hits(haystack, terms)]


def _source_counts(items: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = f"{item.get('source_type')}:{item.get('page_category')}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _public_refs(evidence: list[Evidence], candidate_refs: dict[str, object]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {key: [] for key in REF_PATTERNS}
    for key in ["github_urls", "linkedin_urls", "other_urls"]:
        candidate_values = candidate_refs.get(key, [])
        for value in candidate_values if isinstance(candidate_values, list) else []:
            _append_classified_ref(refs, str(value), fallback_other=key == "other_urls")

    for item in evidence:
        for link in _metadata_links(item) + _metadata_external_links(item) + [item.url]:
            _append_classified_ref(refs, link)
    return refs


def _public_emails(evidence: list[Evidence]) -> list[str]:
    emails: list[str] = []
    for item in evidence:
        for match in re.findall(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", item.text, flags=re.I):
            if any(prefix in match.lower() for prefix in ["support@", "sales@", "info@", "contact@", "hello@"]):
                _append_ref(emails, match)
    return emails[:12]


def _metadata_links(item: Evidence) -> list[str]:
    value = item.metadata.get("links", [])
    return [str(link) for link in value if isinstance(link, str)] if isinstance(value, list) else []


def _metadata_external_links(item: Evidence) -> list[str]:
    value = item.metadata.get("external_links", [])
    return [str(link) for link in value if isinstance(link, str)] if isinstance(value, list) else []


def _append_classified_ref(refs: dict[str, list[str]], link: str, *, fallback_other: bool = False) -> None:
    lower = link.lower()
    matched = False
    for key, patterns in REF_PATTERNS.items():
        if key == "other_urls":
            continue
        if any(pattern in lower for pattern in patterns):
            _append_ref(refs[key], link)
            matched = True
    if fallback_other and not matched:
        _append_ref(refs["other_urls"], link)


def _intelligence_coverage(refs: dict[str, list[str]], evidence_metadata: list[dict[str, object]]) -> dict[str, bool]:
    source_categories = {str(item.get("page_category", "")) for item in evidence_metadata}
    signal_tags = {tag for item in evidence_metadata for tag in item.get("signal_tags", []) if isinstance(tag, str)}
    return {
        "has_website_evidence": bool(evidence_metadata),
        "has_social_profile": bool(refs.get("linkedin_urls") or refs.get("social_urls")),
        "has_github_profile": bool(refs.get("github_urls")),
        "has_marketplace_profile": bool(refs.get("marketplace_urls")),
        "has_docs_or_api": bool(refs.get("docs_urls") or "docs" in source_categories or "integration" in signal_tags),
        "has_pricing_or_commercial": bool(refs.get("pricing_urls") or "pricing" in source_categories or "commercial" in signal_tags),
        "has_contact_path": bool(refs.get("contact_urls")),
    }


def _append_ref(values: list[str], value: str) -> None:
    cleaned = value.strip()
    if cleaned and cleaned not in values:
        values.append(cleaned)
