import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from icp_engine.enrichment import _interesting_links, _is_public_fetch_url, fetch_company_evidence, normalize_domain
from icp_engine.models import CompanyInput


class EnrichmentTests(unittest.TestCase):
    def test_interesting_links_keeps_same_domain_ai_paths(self):
        links = [
            "https://www.geotab.com/products/ace-ai-assistant/",
            "https://external.example/products/ai",
            "mailto:test@example.com",
            "https://geotab.com/about",
        ]

        with patch("icp_engine.enrichment.socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.return_value = [
                (None, None, None, "", ("8.8.8.8", 443)),
            ]
            result = _interesting_links(links, "geotab.com")

        self.assertEqual(result, ["https://www.geotab.com/products/ace-ai-assistant/"])

    def test_normalize_domain_strips_userinfo_and_paths(self):
        self.assertEqual(normalize_domain("https://user:pass@example.com/path"), "example.com")
        self.assertEqual(normalize_domain("example.com/pricing"), "example.com")

    def test_public_fetch_url_rejects_private_network_targets(self):
        self.assertFalse(_is_public_fetch_url("https://localhost/"))
        self.assertFalse(_is_public_fetch_url("https://127.0.0.1:8443/"))
        self.assertFalse(_is_public_fetch_url("http://169.254.169.254/latest/meta-data/"))
        self.assertFalse(_is_public_fetch_url("file:///etc/passwd"))

    def test_public_fetch_url_rejects_domains_resolving_to_private_ips(self):
        with patch("icp_engine.enrichment.socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.return_value = [
                (None, None, None, "", ("10.0.0.5", 443)),
            ]

            self.assertFalse(_is_public_fetch_url("https://internal.example/"))

    def test_fetch_company_evidence_fetches_public_resource_refs_and_skips_linkedin(self):
        fetched_urls = []

        def fake_fetch(url, cache_dir, timeout_seconds):
            fetched_urls.append(url)
            return {
                "url": url,
                "title": url.split("/")[2],
                "text": f"{url} workflow API integration evidence",
                "links": [],
            }

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("icp_engine.enrichment._is_public_fetch_url", return_value=True),
                patch("icp_engine.enrichment._fetch_or_read_cache", side_effect=fake_fetch),
            ):
                evidence, warnings = fetch_company_evidence(
                    CompanyInput(company="Mojio", domain="moj.io"),
                    cache_dir=Path(tmp),
                    max_pages=4,
                    extra_urls=[
                        "https://github.com/mojio",
                        "https://www.linkedin.com/company/mojio",
                    ],
                )

        urls = [item.url for item in evidence]
        self.assertIn("https://github.com/mojio", urls)
        self.assertNotIn("https://www.linkedin.com/company/mojio", fetched_urls)
        self.assertTrue(any("LinkedIn URLs were recorded" in warning for warning in warnings))
        github_item = next(item for item in evidence if item.url == "https://github.com/mojio")
        self.assertEqual(github_item.source_type, "github")
        self.assertEqual(github_item.metadata["page_category"], "profile")

    def test_fetch_stops_after_failure_cap(self):
        company = CompanyInput(company="Blocked", domain="blocked.example")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("icp_engine.enrichment._is_public_fetch_url", return_value=True),
                patch("icp_engine.enrichment._fetch_or_read_cache", side_effect=TimeoutError("slow")),
            ):
                evidence, warnings = fetch_company_evidence(
                    company,
                    Path(tmp),
                    timeout_seconds=0.01,
                    max_pages=5,
                    max_attempts=10,
                    max_failures=3,
                )

        self.assertEqual(evidence, [])
        self.assertTrue(any("failure cap" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
