from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.title = ""
        self._in_title = False
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"] or "")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
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


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lower = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lower]
