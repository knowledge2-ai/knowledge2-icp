from __future__ import annotations

import unittest

from icp_engine.text import extract_published_date, html_to_text, html_to_text_and_links


class ChromeStrippingTest(unittest.TestCase):
    """Page chrome (nav / header / footer / cookie banners) routinely lists every
    industry a parent group or platform serves. Folded into the body text it makes a
    single-vertical incumbent look like a horizontal that names 5 markets, tripping
    the vertical-scatter gate. The extractor must drop chrome text while keeping the
    real body — and must still surface chrome links so crawl discovery survives."""

    def test_nav_mega_menu_industries_excluded_from_text(self) -> None:
        html = (
            "<header><nav>Industries Automotive Construction Education Healthcare "
            "Manufacturing Public Sector</nav></header>"
            "<main><h1>Ibcos Gold</h1><p>Dealer management software for agricultural "
            "and groundcare equipment dealers.</p></main>"
        )
        _, text = html_to_text(html)
        self.assertIn("agricultural", text)
        self.assertIn("Dealer management", text)
        for chrome_term in ("Automotive", "Construction", "Education", "Healthcare", "Public Sector"):
            self.assertNotIn(chrome_term, text)

    def test_footer_industries_list_excluded(self) -> None:
        html = (
            "<main><p>Property management for residential landlords.</p></main>"
            "<footer>Industries we serve: automotive banking healthcare logistics legal "
            "retail manufacturing</footer>"
        )
        _, text = html_to_text(html)
        self.assertIn("Property management", text)
        for chrome_term in ("automotive", "banking", "healthcare", "logistics", "legal"):
            self.assertNotIn(chrome_term, text)

    def test_div_role_and_class_chrome_excluded(self) -> None:
        html = (
            '<div class="site-footer">Solutions for automotive construction education '
            'manufacturing</div>'
            '<div role="navigation">Banking Insurance Mortgage Lending</div>'
            "<main><p>Veterinary practice management.</p></main>"
        )
        _, text = html_to_text(html)
        self.assertIn("Veterinary", text)
        for chrome_term in ("automotive", "construction", "Banking", "Insurance", "Mortgage"):
            self.assertNotIn(chrome_term, text)

    def test_chrome_links_still_collected_for_crawl_discovery(self) -> None:
        html = (
            '<nav><a href="/product">Product</a><a href="/pricing">Pricing</a></nav>'
            '<main><p>Body</p><a href="/case-studies">Stories</a></main>'
        )
        _, _, links = html_to_text_and_links(html, "https://example.com/")
        self.assertIn("https://example.com/product", links)
        self.assertIn("https://example.com/pricing", links)
        self.assertIn("https://example.com/case-studies", links)

    def test_real_body_content_preserved(self) -> None:
        html = (
            "<main><article><section>"
            "<p>Our construction ERP unifies accounting, field service and maintenance "
            "for specialty contractors.</p>"
            "</section></article></main>"
        )
        _, text = html_to_text(html)
        self.assertIn("construction ERP", text)
        self.assertIn("specialty contractors", text)

    def test_content_div_not_falsely_treated_as_chrome(self) -> None:
        # A class containing a chrome-ish substring (e.g. "header-hero") is real
        # content, not chrome — only exact chrome tokens should be stripped.
        html = '<div class="header-hero"><p>Logistics and freight visibility platform.</p></div>'
        _, text = html_to_text(html)
        self.assertIn("Logistics", text)
        self.assertIn("freight visibility", text)


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
