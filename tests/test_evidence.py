import unittest

from icp_engine.evidence import dedupe_evidence, is_high_value_url, select_prompt_evidence
from icp_engine.models import Evidence


class EvidenceSelectionTests(unittest.TestCase):
    def test_dedupe_removes_www_and_same_text_duplicates(self):
        items = [
            Evidence("e1", "https://example.com/products", "Products", "Same product platform text."),
            Evidence("e2", "https://www.example.com/products/", "Products", "Same product platform text."),
            Evidence("e3", "https://example.com/docs", "Docs", "API documentation and integrations."),
        ]

        deduped = dedupe_evidence(items)

        self.assertEqual([item.url for item in deduped], ["https://example.com/products", "https://example.com/docs"])
        self.assertEqual([item.evidence_id for item in deduped], ["e1", "e2"])

    def test_prompt_selection_prefers_ai_docs_over_homepage(self):
        items = [
            Evidence("e1", "https://example.com", "Home", "Software platform for teams."),
            Evidence(
                "e2",
                "https://example.com/docs/ai-assistant",
                "AI assistant docs",
                "AI assistant documentation with permissions, audit, workflow, API, and security controls.",
            ),
            Evidence("e3", "https://example.com/about", "About", "Founded in 2012 with many customers."),
        ]

        selected = select_prompt_evidence(items, limit=2, snippet_chars=200)

        self.assertEqual(selected[0].evidence_id, "e2")
        self.assertIn("AI assistant", selected[0].text)

    def test_prompt_snippet_keeps_ai_writer_context(self):
        items = [
            Evidence(
                "e1",
                "https://example.com/products",
                "Products",
                "Navigation and generic product copy. " * 20
                + "Social media management features include an AI writer and AI content generator with approvals.",
            )
        ]

        selected = select_prompt_evidence(items, limit=1, snippet_chars=240)

        self.assertIn("AI writer", selected[0].text)

    def test_short_ai_url_term_does_not_match_unrelated_words(self):
        self.assertFalse(is_high_value_url("https://example.com/solutions/sustainable-fleet"))
        self.assertTrue(is_high_value_url("https://example.com/products/ai-assistant"))


if __name__ == "__main__":
    unittest.main()
