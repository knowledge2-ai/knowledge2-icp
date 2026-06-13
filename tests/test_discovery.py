from __future__ import annotations

import unittest

from icp_engine.discovery import candidates_from_links, candidates_from_serper_payload, discover_companies, discover_companies_from_url, extract_page_links, extract_search_links, parse_seed_companies


SEARCH_HTML = """
<html>
  <body>
    <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.moj.io%2F">Mojio - Connected Mobility Platform</a>
    <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.automate.co.za%2F">Automate | Dealer Management Software</a>
    <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.linkedin.com%2Fcompany%2Fmojio">Mojio LinkedIn</a>
    <a class="result__a" href="/l/?uddg=https%3A%2F%2Fgithub.com%2Fmojio">GitHub - mojio</a>
    <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.crunchbase.com%2Forganization%2Fmojio">Mojio - Crunchbase</a>
  </body>
</html>
"""


class DiscoveryTest(unittest.TestCase):
    def test_extract_search_links_and_candidates(self) -> None:
        links = extract_search_links(SEARCH_HTML)
        candidates = candidates_from_links(links, max_results=5)

        self.assertEqual([item.domain for item in candidates], ["moj.io", "automate.co.za"])
        self.assertEqual(candidates[0].company, "Mojio")
        self.assertEqual(candidates[0].linkedin_urls, ["https://www.linkedin.com/company/mojio"])
        self.assertEqual(candidates[0].github_urls, ["https://github.com/mojio"])
        self.assertEqual(candidates[0].other_urls, ["https://www.crunchbase.com/organization/mojio"])

    def test_candidates_keep_profile_refs_after_max_company_limit(self) -> None:
        links = extract_search_links(SEARCH_HTML)
        candidates = candidates_from_links(links, max_results=1)

        self.assertEqual([item.domain for item in candidates], ["moj.io"])
        self.assertEqual(candidates[0].linkedin_urls, ["https://www.linkedin.com/company/mojio"])

    def test_discover_companies_uses_injected_fetcher(self) -> None:
        candidates, warnings = discover_companies("fleet software", fetcher=lambda _: SEARCH_HTML)

        self.assertFalse(warnings)
        self.assertEqual(candidates[1].domain, "automate.co.za")

    def test_discover_companies_from_portfolio_url(self) -> None:
        html = """
        <html><body>
          <a href="https://www.moj.io/">Mojio connected mobility</a>
          <a href="https://www.automate.co.za/">Automate dealer software</a>
          <a href="/portfolio/internal">Internal page</a>
        </body></html>
        """

        links = extract_page_links(html, base_url="https://portfolio.example/list")
        candidates, warnings = discover_companies_from_url("https://portfolio.example/list", fetcher=lambda _: html)

        self.assertIn(("https://www.moj.io/", "Mojio connected mobility"), links)
        self.assertFalse(warnings)
        self.assertEqual([item.domain for item in candidates[:2]], ["moj.io", "automate.co.za"])

    def test_candidates_from_serper_payload(self) -> None:
        candidates = candidates_from_serper_payload(
            {
                "organic": [
                    {
                        "title": "ServiceTitan - Software for the Trades",
                        "link": "https://www.servicetitan.com/",
                        "snippet": "Field service workflow platform.",
                    },
                    {
                        "title": "LinkedIn ServiceTitan",
                        "link": "https://www.linkedin.com/company/servicetitan",
                    },
                    {
                        "title": "Samsara: Connected Operations",
                        "link": "https://samsara.com/",
                    },
                ]
            },
            max_results=5,
        )

        self.assertEqual([item.domain for item in candidates], ["servicetitan.com", "samsara.com"])
        self.assertEqual(candidates[0].company, "ServiceTitan")

    def test_parse_seed_companies_accepts_csvish_lines(self) -> None:
        candidates = parse_seed_companies("Mojio, moj.io\nAutomate | automate.co.za\n")

        self.assertEqual(candidates[0].company, "Mojio")
        self.assertEqual(candidates[1].domain, "automate.co.za")


if __name__ == "__main__":
    unittest.main()
