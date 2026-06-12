import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from icp_engine.enrichment import _interesting_links, fetch_company_evidence
from icp_engine.models import CompanyInput


class EnrichmentTests(unittest.TestCase):
    def test_interesting_links_keeps_same_domain_ai_paths(self):
        links = [
            "https://www.geotab.com/products/ace-ai-assistant/",
            "https://external.example/products/ai",
            "mailto:test@example.com",
            "https://geotab.com/about",
        ]

        result = _interesting_links(links, "geotab.com")

        self.assertEqual(result, ["https://www.geotab.com/products/ace-ai-assistant/"])

    def test_fetch_stops_after_failure_cap(self):
        company = CompanyInput(company="Blocked", domain="blocked.example")

        with TemporaryDirectory() as tmp:
            with patch("icp_engine.enrichment._fetch_or_read_cache", side_effect=TimeoutError("slow")):
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
