from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from .models import Evidence
from .text import compact_snippet, normalize_whitespace


# Recency shaping for outreach selection (soft downweight): a fresh page gets up
# to +RECENCY_BONUS, decaying to 0 at the window edge; an older page is penalized
# up to -2*RECENCY_PENALTY. Tuned so recency reorders the term ranking without
# zeroing it — a strong old page still outranks a weak fresh one.
RECENCY_BONUS = 8
RECENCY_PENALTY = 6
DEFAULT_RECENCY_WINDOW_DAYS = 365


AI_TERMS = [
    " ai ",
    "ai ",
    " ai-",
    "artificial intelligence",
    "generative ai",
    "ai-powered",
    "ai writer",
    "ai content",
    "ai assistant",
    "ai-driven",
    "machine learning",
    "copilot",
    "assistant",
    "chatgpt",
    "gpt",
    "llm",
    "agentic",
    "summarize",
    "writer",
    "chatbot",
    "plain language",
]

SUBSTANCE_TERMS = [
    "docs",
    "documentation",
    "pricing",
    "case study",
    "customers",
    "changelog",
    "release",
    "permissions",
    "governance",
    "audit",
    "evaluation",
    "evals",
    "workflow",
    "integration",
    "api",
    "security",
    "sso",
]

DATA_TERMS = [
    "workflow",
    "documents",
    "records",
    "transactions",
    "inventory",
    "tickets",
    "claims",
    "telematics",
    "trips",
    "diagnostics",
    "dispatch",
    "analytics",
    "reporting",
]

HIGH_VALUE_PATH_TERMS = [
    "ai",
    "artificial-intelligence",
    "copilot",
    "assistant",
    "gpt",
    "docs",
    "developers",
    "api",
    "pricing",
    "case-studies",
    "customers",
    "changelog",
    "blog",
    "news",
    "product",
    "platform",
]

DISCOVERY_PATH_TERMS = HIGH_VALUE_PATH_TERMS + [
    "ace",
    "intelligence",
    "automation",
    "insights",
]


@dataclass(frozen=True)
class EvidencePromptItem:
    evidence_id: str
    url: str
    title: str
    signal_score: int
    text: str
    published_at: str | None = None


def dedupe_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[str] = set()
    deduped: list[Evidence] = []
    for item in items:
        keys = {_canonical_url(item.url), _text_fingerprint(item.text)}
        if seen.intersection(keys):
            continue
        seen.update(keys)
        deduped.append(item)
    return [
        Evidence(
            evidence_id=f"e{index}",
            url=item.url,
            title=item.title,
            text=item.text,
            source_type=item.source_type,
            metadata=dict(item.metadata),
        )
        for index, item in enumerate(deduped, start=1)
    ]


def select_prompt_evidence(
    items: list[Evidence],
    *,
    limit: int = 10,
    snippet_chars: int = 900,
    reference_date: date | None = None,
    recency_window_days: int = DEFAULT_RECENCY_WINDOW_DAYS,
) -> list[EvidencePromptItem]:
    """Rank evidence for an outreach prompt by signal strength, downweighted by age.

    Recency is a soft force (see ``_recency_adjustment``): fresh pages rise, stale
    pages sink, undated pages are neutral — but a strong old page can still surface
    if nothing fresher carries the signal. ``reference_date`` is injectable so the
    ranking is deterministic in tests; it defaults to today in production.
    """
    reference_date = reference_date or date.today()
    ranked = sorted(
        items,
        key=lambda item: _evidence_rank(item) + _recency_adjustment(item, reference_date, recency_window_days),
        reverse=True,
    )
    selected: list[EvidencePromptItem] = []
    seen_snippets: set[str] = set()
    for item in ranked:
        snippet = _signal_snippet(item, snippet_chars)
        fingerprint = _text_fingerprint(snippet[:700])
        if fingerprint in seen_snippets:
            continue
        seen_snippets.add(fingerprint)
        published_at = item.metadata.get("published_at") if isinstance(item.metadata, dict) else None
        selected.append(
            EvidencePromptItem(
                evidence_id=item.evidence_id,
                url=item.url,
                title=item.title,
                signal_score=_evidence_rank(item),
                text=snippet,
                published_at=str(published_at) if published_at else None,
            )
        )
        if len(selected) >= limit:
            break
    return selected


def _parse_iso_date(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _recency_adjustment(item: Evidence, reference_date: date, window_days: int) -> int:
    """Soft recency shaping for the sort key. Neutral (0) when the page has no date."""
    published = _parse_iso_date(item.metadata.get("published_at") if isinstance(item.metadata, dict) else None)
    if published is None or window_days <= 0:
        return 0
    age_days = max((reference_date - published).days, 0)
    if age_days <= window_days:
        return round(RECENCY_BONUS * (1 - age_days / window_days))
    overage = min((age_days - window_days) / window_days, 2.0)
    return -round(RECENCY_PENALTY * overage)


def _evidence_rank(item: Evidence) -> int:
    haystack = f"{item.url} {item.title} {item.text}".lower()
    score = 0
    score += 12 * _hit_count(haystack, AI_TERMS)
    score += 7 * _hit_count(haystack, SUBSTANCE_TERMS)
    score += 5 * _hit_count(haystack, DATA_TERMS)
    score += 6 * _path_hit_count(item.url, HIGH_VALUE_PATH_TERMS)
    if _is_homepage(item.url):
        score -= 8
    return score


def is_high_value_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(_path_contains_term(path, term) for term in DISCOVERY_PATH_TERMS)


def _signal_snippet(item: Evidence, max_chars: int) -> str:
    text = normalize_whitespace(item.text)
    terms = AI_TERMS + SUBSTANCE_TERMS + DATA_TERMS
    windows = _keyword_windows(text, terms, window_chars=360)
    if not windows:
        return compact_snippet(text, max_chars)
    joined = normalize_whitespace(" ... ".join(windows))
    return compact_snippet(joined, max_chars)


def _keyword_windows(text: str, terms: list[str], *, window_chars: int) -> list[str]:
    lower = text.lower()
    starts: list[int] = []
    for term in terms:
        index = lower.find(term.lower())
        if index != -1:
            starts.append(max(0, index - window_chars // 3))
    windows: list[str] = []
    for start in sorted(set(starts))[:4]:
        end = min(len(text), start + window_chars)
        windows.append(text[start:end].strip())
    return windows


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", parsed.path.lower())
    return f"{host}{path}"


def _text_fingerprint(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
    normalized = normalize_whitespace(normalized)[:2500]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _hit_count(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term.lower() in text)


def _path_hit_count(url: str, terms: list[str]) -> int:
    path = urlparse(url).path.lower()
    return sum(1 for term in terms if _path_contains_term(path, term))


def _path_contains_term(path: str, term: str) -> bool:
    if len(term) <= 3:
        return re.search(rf"(^|[-_/]){re.escape(term)}($|[-_/])", path) is not None
    return term in path


def _is_homepage(url: str) -> bool:
    path = re.sub(r"/+$", "", urlparse(url).path)
    return path in {"", "/"}
