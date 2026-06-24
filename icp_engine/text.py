from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin


# Tags whose text is never page content.
_SKIP_TAGS = {"script", "style", "noscript", "svg"}
# Semantic chrome: site nav, banners, footers, and sidebars. Their text routinely
# lists every industry a parent group or platform serves, which contaminates the
# vertical signal of a single-vertical incumbent. Stripped from text — but their
# links are still collected so crawl discovery (product/pricing/docs pages) survives.
_CHROME_TAGS = {"nav", "header", "footer", "aside"}
_CHROME_ROLES = {"navigation", "banner", "contentinfo", "menu", "menubar", "search"}
_CHROME_CLASS_TOKENS = {
    "nav", "navbar", "navigation", "menu", "megamenu", "mega-menu", "header",
    "site-header", "masthead", "footer", "site-footer", "breadcrumb", "breadcrumbs",
    "cookie", "cookies", "cookie-banner", "sidebar",
}
_CHROME_CLASS_SUFFIXES = ("-nav", "-navbar", "-navigation", "-menu", "-footer", "-header")
_CHROME_CLASS_PREFIXES = ("nav-", "navbar-", "menu-", "megamenu-", "footer-")
# Void elements never get a matching end tag, so they must not be pushed onto the
# open-tag stack or it would never balance.
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}


def _is_chrome_element(tag: str, attrs_dict: dict[str, str | None]) -> bool:
    if tag in _CHROME_TAGS:
        return True
    role = (attrs_dict.get("role") or "").strip().lower()
    if role in _CHROME_ROLES:
        return True
    identifiers = f"{attrs_dict.get('class') or ''} {attrs_dict.get('id') or ''}".lower()
    for token in identifiers.split():
        if token in _CHROME_CLASS_TOKENS:
            return True
        if token.endswith(_CHROME_CLASS_SUFFIXES) or token.startswith(_CHROME_CLASS_PREFIXES):
            return True
    return False


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.title = ""
        self._in_title = False
        self.parts: list[str] = []
        self.links: list[str] = []
        # Stack of currently-open non-void tags, and the stack depth at which the
        # outermost enclosing chrome element began (None when not inside chrome).
        self._open_tags: list[str] = []
        self._chrome_floor: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = dict(attrs)
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        # Links are collected even inside chrome so nav/footer links still feed
        # crawl discovery; only the chrome *text* is dropped.
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"] or "")
        if tag in _VOID_TAGS:
            return
        if self._chrome_floor is None and _is_chrome_element(tag, attrs_dict):
            self._chrome_floor = len(self._open_tags)
        self._open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in _VOID_TAGS:
            return
        # Pop back to (and including) the most recent matching open tag, tolerating
        # unclosed children, so malformed markup can't strand the stack.
        if tag in self._open_tags:
            while self._open_tags:
                popped = self._open_tags.pop()
                if popped == tag:
                    break
        if self._chrome_floor is not None and len(self._open_tags) <= self._chrome_floor:
            self._chrome_floor = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._chrome_floor is not None:
            return
        cleaned = normalize_whitespace(data)
        if not cleaned:
            return
        if self._in_title:
            self.title = normalize_whitespace(f"{self.title} {cleaned}")
        self.parts.append(cleaned)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def html_to_text(html: str) -> tuple[str, str]:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.title, normalize_whitespace(" ".join(parser.parts))


def html_to_text_and_links(html: str, base_url: str) -> tuple[str, str, list[str]]:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    links = [urljoin(base_url, link) for link in parser.links if link and not link.startswith("#")]
    return parser.title, normalize_whitespace(" ".join(parser.parts)), links


def compact_snippet(text: str, max_chars: int = 700) -> str:
    text = normalize_whitespace(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""([a-zA-Z:.\-_]+)\s*=\s*["']([^"']*)["']""")
_JSONLD_DATE_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.IGNORECASE)
_TIME_RE = re.compile(r"""<time\b[^>]*\bdatetime\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_DATE_META_KEYS = {
    "article:published_time",
    "date",
    "pubdate",
    "publishdate",
    "publication_date",
    "dc.date",
    "dc.date.issued",
    "datepublished",
}


def _to_iso_date(raw: str | None) -> str | None:
    """Normalize a date string (ISO 8601 or RFC 2822/Last-Modified) to YYYY-MM-DD."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(candidate).date().isoformat()
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    return parsed.date().isoformat() if parsed is not None else None


def _meta_published_date(html: str) -> str | None:
    for tag in _META_TAG_RE.findall(html):
        attrs = {key.lower(): value for key, value in _ATTR_RE.findall(tag)}
        key = attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or ""
        if key.lower() in _DATE_META_KEYS:
            iso = _to_iso_date(attrs.get("content"))
            if iso:
                return iso
    return None


def extract_published_date(html: str, last_modified: str | None = None) -> tuple[str | None, str]:
    """Best-effort publish date for a fetched page.

    Prefers an in-page published date (the blog/news/changelog/press pages that
    actually go stale): ``<meta property="article:published_time">`` and kin,
    JSON-LD ``datePublished``, then ``<time datetime>``. Falls back to the HTTP
    ``Last-Modified`` header. Returns ``(YYYY-MM-DD, source)`` or ``(None, "none")``
    when nothing parseable is found — undated pages are neutral downstream, not stale.
    """
    meta = _meta_published_date(html)
    if meta:
        return meta, "meta"
    for match in _JSONLD_DATE_RE.findall(html):
        iso = _to_iso_date(match)
        if iso:
            return iso, "jsonld"
    for match in _TIME_RE.findall(html):
        iso = _to_iso_date(match)
        if iso:
            return iso, "time"
    header = _to_iso_date(last_modified)
    if header:
        return header, "last-modified"
    return None, "none"


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lower = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lower]


def keyword_hits_boundary(text: str, keywords: list[str]) -> list[str]:
    """Like ``keyword_hits`` but matches on word boundaries, so a short term such
    as ``erp`` does not falsely match inside ``enterprise``. Used for the vertical
    signal, where substring collisions would otherwise fire for almost every B2B
    company and wash out the vertical-focus signal entirely."""
    lower = text.lower()
    return [
        keyword
        for keyword in keywords
        if re.search(rf"\b{re.escape(keyword.lower())}\b", lower)
    ]


def keyword_counts_boundary(text: str, keywords: list[str]) -> dict[str, int]:
    """Word-boundary occurrence counts for each keyword present in the text.

    Lets a caller tell genuine focus (one vertical term repeated throughout the
    copy) from incidental name-drops (many verticals each mentioned once) — the
    discriminator between a vertical incumbent and a horizontal platform that
    merely lists the industries it serves."""
    lower = text.lower()
    counts: dict[str, int] = {}
    for keyword in keywords:
        matches = re.findall(rf"\b{re.escape(keyword.lower())}\b", lower)
        if matches:
            counts[keyword] = len(matches)
    return counts
