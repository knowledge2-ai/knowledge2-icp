import unittest

from icp_engine.apollo_reveal_check import _verdict, mask_email, mask_name, summarize


class ApolloRevealCheckTest(unittest.TestCase):
    def test_mask_email(self) -> None:
        self.assertEqual(mask_email("jane.doe@stripe.com"), "j***@stripe.com")
        self.assertEqual(mask_email(""), "")
        self.assertEqual(mask_email("not-an-email"), "not-an-email")

    def test_mask_name(self) -> None:
        self.assertEqual(mask_name("Jane Doe"), "J.D.")
        self.assertEqual(mask_name("  "), "")

    def test_summarize_counts_revealed_and_masks_by_default(self) -> None:
        people = [
            {"name": "Jane Doe", "title": "CPO", "email": "jane@stripe.com", "email_status": "verified"},
            {"name": "John Roe", "title": "CTO", "email": "", "email_status": "available_unrevealed"},
        ]
        report = summarize(people, reveal=False)
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["revealed"], 1)
        # Masked: real email never appears in the row.
        self.assertEqual(report["rows"][0]["email"], "j***@stripe.com")
        self.assertEqual(report["rows"][0]["name"], "J.D.")
        # Unrevealed contact reads honestly.
        self.assertFalse(report["rows"][1]["revealed"])
        self.assertEqual(report["rows"][1]["email"], "(none)")

    def test_summarize_reveal_shows_full(self) -> None:
        people = [{"name": "Jane Doe", "title": "CPO", "email": "jane@stripe.com"}]
        report = summarize(people, reveal=True)
        self.assertEqual(report["rows"][0]["email"], "jane@stripe.com")
        self.assertEqual(report["rows"][0]["name"], "Jane Doe")

    def test_verdict(self) -> None:
        self.assertIn("NO RESULTS", _verdict(0, 0))
        self.assertIn("NO PII", _verdict(3, 0))
        self.assertIn("REVEAL WORKS", _verdict(3, 2))


if __name__ == "__main__":
    unittest.main()
