import unittest
from datetime import date

from icp_engine.evidence import (
    RECENCY_BONUS,
    RECENCY_PENALTY,
    _recency_adjustment,
    dedupe_evidence,
    is_high_value_url,
    select_prompt_evidence,
)
from icp_engine.models import Evidence


class EvidenceSelectionTests(unittest.TestCase):
    def test_dedupe_removes_www_and_same_text_duplicates(self):
        items = [
            Evidence(
                "e1",
                "https://example.com/products",
                "Products",
                "Same product platform text.",
                metadata={"page_category": "product", "links": ["https://github.com/example"]},
            ),
            Evidence("e2", "https://www.example.com/products/", "Products", "Same product platform text."),
            Evidence("e3", "https://example.com/docs", "Docs", "API documentation and integrations."),
        ]

        deduped = dedupe_evidence(items)

        self.assertEqual([item.url for item in deduped], ["https://example.com/products", "https://example.com/docs"])
        self.assertEqual([item.evidence_id for item in deduped], ["e1", "e2"])
        self.assertEqual(deduped[0].metadata["page_category"], "product")

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


REF = date(2026, 1, 1)


class RecencyAdjustmentTest(unittest.TestCase):
    def _ev(self, published: str | None) -> Evidence:
        meta = {"published_at": published} if published is not None else {}
        return Evidence("e1", "https://x.com/p", "P", "text", metadata=meta)

    def test_fresh_today_gets_full_bonus(self):
        self.assertEqual(_recency_adjustment(self._ev("2026-01-01"), REF, 365), RECENCY_BONUS)

    def test_window_edge_is_zero(self):
        self.assertEqual(_recency_adjustment(self._ev("2025-01-01"), REF, 365), 0)

    def test_old_page_is_penalized(self):
        # ~2x window old -> overage 1.0 -> -RECENCY_PENALTY.
        self.assertEqual(_recency_adjustment(self._ev("2024-01-01"), REF, 365), -RECENCY_PENALTY)

    def test_undated_is_neutral(self):
        self.assertEqual(_recency_adjustment(self._ev(None), REF, 365), 0)

    def test_unparseable_date_is_neutral(self):
        self.assertEqual(_recency_adjustment(self._ev("garbage"), REF, 365), 0)


class RecencySelectionTest(unittest.TestCase):
    def test_fresh_outranks_stale_at_equal_signal(self):
        # Same signal terms (equal _evidence_rank), distinct filler (no dedupe);
        # recency alone decides order.
        fresh = Evidence("e1", "https://x.com/blog/new", "New", "generative ai data workflow analytics platform shipped today.", metadata={"published_at": "2025-12-15"})
        stale = Evidence("e2", "https://x.com/blog/old", "Old", "generative ai data workflow analytics platform overview here.", metadata={"published_at": "2019-01-01"})
        selected = select_prompt_evidence([stale, fresh], limit=2, reference_date=REF)
        self.assertEqual([item.evidence_id for item in selected], ["e1", "e2"])
        self.assertEqual(selected[0].published_at, "2025-12-15")

    def test_strong_old_still_beats_weak_fresh(self):
        # Soft downweight: a keyword-rich old page outranks a content-thin fresh one.
        strong_old = Evidence("e1", "https://x.com/ai-platform", "AI", "generative ai artificial intelligence ai-powered data analytics workflow automation platform.", metadata={"published_at": "2019-01-01"})
        weak_fresh = Evidence("e2", "https://x.com/team", "Team", "Meet the people on our team.", metadata={"published_at": "2025-12-31"})
        selected = select_prompt_evidence([weak_fresh, strong_old], limit=2, reference_date=REF)
        self.assertEqual(selected[0].evidence_id, "e1")

    def test_undated_evidence_keeps_signal_order(self):
        # No dates anywhere -> recency is a no-op, pure signal ranking stands.
        high = Evidence("e1", "https://x.com/ai", "AI", "generative ai data analytics workflow platform.")
        low = Evidence("e2", "https://x.com/about", "About", "Company background and history.")
        selected = select_prompt_evidence([low, high], limit=2, reference_date=REF)
        self.assertEqual(selected[0].evidence_id, "e1")


if __name__ == "__main__":
    unittest.main()
