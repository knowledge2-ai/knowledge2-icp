from __future__ import annotations

import unittest

from icp_engine.metadata import classify_source, lead_metadata_summary
from icp_engine.models import CompanyInput, Evidence


class MetadataTest(unittest.TestCase):
    def test_classify_source_uses_url_and_metadata(self) -> None:
        self.assertEqual(classify_source("https://example.com/docs/api")["page_category"], "docs")
        self.assertEqual(classify_source("https://github.com/acme")["source_type"], "github")
        self.assertEqual(classify_source("https://www.g2.com/products/acme")["page_category"], "profile")
        self.assertEqual(
            classify_source("https://example.com/anything", {"page_category": "pricing"})["page_category"],
            "pricing",
        )

    def test_lead_metadata_summary_extracts_refs_and_signals(self) -> None:
        company = CompanyInput(company="Acme Fleet", domain="acme.example")
        evidence = [
            Evidence(
                "e1",
                "https://acme.example/platform",
                "Platform",
                "Fleet workflow analytics, API integrations, enterprise customers, and permissions.",
                metadata={
                    "page_category": "product",
                    "links": [
                        "https://www.linkedin.com/company/acme-fleet",
                        "https://github.com/acme",
                        "https://x.com/acmefleet",
                        "https://acme.example/pricing",
                    ],
                    "external_links": ["https://www.g2.com/products/acme-fleet"],
                },
            )
        ]

        summary = lead_metadata_summary(
            company,
            evidence,
            {"other_urls": ["https://www.crunchbase.com/organization/acme-fleet"]},
        )

        self.assertIn("website:product", summary["source_counts"])
        self.assertIn("workflow", summary["signal_tags"])
        self.assertIn("https://github.com/acme", summary["source_refs"]["github_urls"])
        self.assertIn("https://x.com/acmefleet", summary["source_refs"]["social_urls"])
        self.assertIn("https://www.g2.com/products/acme-fleet", summary["source_refs"]["marketplace_urls"])
        self.assertIn("https://www.crunchbase.com/organization/acme-fleet", summary["source_refs"]["marketplace_urls"])
        self.assertIn("https://acme.example/pricing", summary["source_refs"]["pricing_urls"])
        self.assertTrue(summary["intelligence_coverage"]["has_social_profile"])
        self.assertTrue(summary["intelligence_coverage"]["has_marketplace_profile"])


if __name__ == "__main__":
    unittest.main()
