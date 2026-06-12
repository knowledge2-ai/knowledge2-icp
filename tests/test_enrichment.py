import unittest

from icp_engine.enrichment import _interesting_links


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


if __name__ == "__main__":
    unittest.main()
