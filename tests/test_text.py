from __future__ import annotations

import unittest

from icp_engine.text import extract_published_date


class ExtractPublishedDateTest(unittest.TestCase):
    def test_meta_article_published_time_wins(self) -> None:
        html = '<head><meta property="article:published_time" content="2025-09-12T10:00:00Z"></head>'
        self.assertEqual(extract_published_date(html), ("2025-09-12", "meta"))

    def test_meta_attr_order_is_irrelevant(self) -> None:
        # content before the name attr must still parse.
        html = '<meta content="2024-03-01" name="date">'
        self.assertEqual(extract_published_date(html), ("2024-03-01", "meta"))

    def test_jsonld_date_published(self) -> None:
        html = '<script type="application/ld+json">{"@type":"Article","datePublished":"2025-01-05"}</script>'
        self.assertEqual(extract_published_date(html), ("2025-01-05", "jsonld"))

    def test_time_datetime_attribute(self) -> None:
        html = '<article><time datetime="2023-11-30T08:00:00+00:00">Nov 30</time></article>'
        self.assertEqual(extract_published_date(html), ("2023-11-30", "time"))

    def test_meta_preferred_over_jsonld_and_time(self) -> None:
        html = (
            '<meta property="article:published_time" content="2025-06-01">'
            '<script>{"datePublished":"2010-01-01"}</script>'
            '<time datetime="2009-01-01">old</time>'
        )
        self.assertEqual(extract_published_date(html), ("2025-06-01", "meta"))

    def test_falls_back_to_last_modified_header(self) -> None:
        result = extract_published_date("<p>no dates here</p>", last_modified="Wed, 21 Oct 2024 07:28:00 GMT")
        self.assertEqual(result, ("2024-10-21", "last-modified"))

    def test_in_page_date_beats_last_modified(self) -> None:
        html = '<meta name="pubdate" content="2025-02-02">'
        result = extract_published_date(html, last_modified="Wed, 21 Oct 2020 07:28:00 GMT")
        self.assertEqual(result, ("2025-02-02", "meta"))

    def test_undated_page_is_none(self) -> None:
        self.assertEqual(extract_published_date("<h1>About us</h1>"), (None, "none"))

    def test_garbage_date_is_ignored(self) -> None:
        html = '<meta name="date" content="not-a-date"><time datetime="">x</time>'
        self.assertEqual(extract_published_date(html), (None, "none"))


if __name__ == "__main__":
    unittest.main()
