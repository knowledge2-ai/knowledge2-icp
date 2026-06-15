from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from icp_engine import bakeoff
from icp_engine.app_store import AppStore
from icp_engine.mining import normalize_clauses
from icp_engine.seed_defaults import SEED_RUN_ID, seeded_run


def _offline_store(tmp: str) -> AppStore:
    return AppStore(Path(tmp) / "state", Path(tmp) / "missing-icp.md")


class FilteringScorerTest(unittest.TestCase):
    def _result(self, *domains: str) -> dict:
        return {"results": [{"domain": domain} for domain in domains]}

    def test_exact_precision_recall_f1(self) -> None:
        gold = {"a.com", "b.com", "c.com"}
        result = self._result("a.com", "b.com", "x.com")  # 2 hits, 1 false positive
        scored = bakeoff.score_filtering(result, gold, [])
        self.assertEqual(scored["true_positives"], 2)
        self.assertAlmostEqual(scored["precision"], 2 / 3, places=4)
        self.assertAlmostEqual(scored["recall"], 2 / 3, places=4)
        self.assertAlmostEqual(scored["f1"], 2 / 3, places=4)

    def test_perfect_match(self) -> None:
        gold = {"a.com", "b.com"}
        scored = bakeoff.score_filtering(self._result("a.com", "b.com"), gold, [])
        self.assertEqual((scored["precision"], scored["recall"], scored["f1"]), (1.0, 1.0, 1.0))

    def test_empty_gold_and_empty_prediction_is_perfect(self) -> None:
        scored = bakeoff.score_filtering(self._result(), set(), [])
        self.assertEqual((scored["precision"], scored["recall"], scored["f1"]), (1.0, 1.0, 1.0))

    def test_empty_gold_with_predictions_is_zero_precision(self) -> None:
        scored = bakeoff.score_filtering(self._result("a.com"), set(), [])
        self.assertEqual(scored["precision"], 0.0)
        self.assertEqual(scored["f1"], 0.0)

    def test_unevaluable_keys_reported(self) -> None:
        clauses = normalize_clauses(
            [{"key": "tier", "op": "==", "value": "A"}, {"key": "has_contact_path", "op": "==", "value": True}]
        )
        scored = bakeoff.score_filtering(self._result("a.com"), {"a.com"}, clauses)
        self.assertEqual(scored["unevaluable_keys"], ["has_contact_path"])


class GroundTruthMatchesTest(unittest.TestCase):
    def test_replays_matches_clauses_exactly(self) -> None:
        records = [
            {"domain": "a.com", "tier": "A", "total_score": 90},
            {"domain": "b.com", "tier": "B", "total_score": 65},
            {"domain": "c.com", "tier": "A", "total_score": 50},
        ]
        clauses = normalize_clauses([{"key": "tier", "op": "==", "value": "A"}, {"key": "total_score", "op": ">=", "value": 80}])
        self.assertEqual(bakeoff.ground_truth_matches(records, clauses), {"a.com"})

    def test_unevaluable_clause_is_skipped_not_excluded(self) -> None:
        records = [{"domain": "a.com", "tier": "A"}, {"domain": "b.com", "tier": "B"}]
        clauses = normalize_clauses([{"key": "has_contact_path", "op": "==", "value": True}])
        # Unevaluable offline → every record passes (surfaced as coverage gap, not excluded).
        self.assertEqual(bakeoff.ground_truth_matches(records, clauses), {"a.com", "b.com"})


class LookalikeScorerTest(unittest.TestCase):
    def test_precision_recall_map_at_k(self) -> None:
        label = {"seed.com": "fintech", "a.com": "fintech", "b.com": "fintech", "c.com": "edtech"}
        # Predicted ranking: hit, miss, hit  → 2 of 3 relevant peers found.
        result = {"results": [{"domain": "a.com"}, {"domain": "c.com"}, {"domain": "b.com"}]}
        scored = bakeoff.score_lookalikes(result, "seed.com", label, k=3)
        self.assertEqual(scored["seed_category"], "fintech")
        self.assertEqual(scored["relevant_count"], 2)
        self.assertEqual(scored["hits"], 2)
        self.assertAlmostEqual(scored["precision_at_k"], 2 / 3, places=4)
        self.assertEqual(scored["recall_at_k"], 1.0)
        # AP = (1/1 at rank1 + 2/3 at rank3) / min(2,3) = (1 + 0.6667) / 2
        self.assertAlmostEqual(scored["map_at_k"], (1.0 + 2 / 3) / 2, places=4)

    def test_no_relevant_peers_zero(self) -> None:
        label = {"seed.com": "solo", "a.com": "other"}
        scored = bakeoff.score_lookalikes({"results": [{"domain": "a.com"}]}, "seed.com", label, k=5)
        self.assertEqual(scored["relevant_count"], 0)
        self.assertEqual(scored["precision_at_k"], 0.0)


class GroundingScorerTest(unittest.TestCase):
    def test_full_coverage_no_contradiction(self) -> None:
        case = {"company": "Acme", "domain": "acme.com", "tier": "A", "signal_tags": ["workflow"]}
        answer = "Acme (acme.com) is Tier A with strong workflow data."
        scored = bakeoff.score_grounding(answer, case)
        self.assertEqual(scored["coverage"], 1.0)
        self.assertFalse(scored["tier_contradiction"])
        self.assertEqual(scored["grounding_score"], 1.0)

    def test_partial_coverage(self) -> None:
        case = {"company": "Acme", "domain": "acme.com", "tier": "A", "signal_tags": []}
        answer = "Acme is a promising account."  # domain + tier missing
        scored = bakeoff.score_grounding(answer, case)
        self.assertEqual(scored["facts_checked"], 3)
        self.assertEqual(scored["facts_surfaced"], 1)
        self.assertAlmostEqual(scored["coverage"], 1 / 3, places=4)

    def test_tier_contradiction_penalizes(self) -> None:
        case = {"company": "Acme", "domain": "acme.com", "tier": "A", "signal_tags": []}
        answer = "Acme (acme.com) is Tier C."  # wrong tier claimed
        scored = bakeoff.score_grounding(answer, case)
        self.assertTrue(scored["tier_contradiction"])
        # company + domain surfaced (2/3 coverage) but tier claim contradicts → penalized to 0.
        self.assertEqual(scored["grounding_score"], 0.0)


class AveragePrecisionTest(unittest.TestCase):
    def test_all_relevant_first(self) -> None:
        self.assertEqual(bakeoff._average_precision(["a", "b", "c"], {"a", "b"}), 1.0)

    def test_empty_relevant_and_empty_predicted(self) -> None:
        self.assertEqual(bakeoff._average_precision([], set()), 1.0)


class OfflineRunBakeoffTest(unittest.TestCase):
    def test_offline_run_is_local_only_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = _offline_store(tmp)
            report = bakeoff.run_bakeoff(store, run_id=SEED_RUN_ID)

        self.assertFalse(report["k2_configured"])
        self.assertEqual(report["run_id"], SEED_RUN_ID)
        self.assertGreater(report["record_count"], 400)
        for dimension in ("filtering", "lookalikes", "grounding"):
            self.assertTrue(report[dimension], f"{dimension} produced no rows")
            for row in report[dimension]:
                self.assertIn("local", row)
                self.assertNotIn("k2", row)  # unconfigured → no K2 column

    def test_local_filtering_reproduces_ground_truth(self) -> None:
        # Local mine uses the same _matches_clauses as the gold, so on evaluable
        # clauses (and a generous top_k) it must reproduce the gold set exactly.
        with tempfile.TemporaryDirectory() as tmp:
            store = _offline_store(tmp)
            report = bakeoff.run_bakeoff(store, run_id=SEED_RUN_ID)
        for row in report["filtering"]:
            self.assertEqual(row["local"]["f1"], 1.0, f"{row['case_id']} local did not reproduce gold")

    def test_csv_and_markdown_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = _offline_store(tmp)
            report = bakeoff.run_bakeoff(store, run_id=SEED_RUN_ID)
        csv_text = bakeoff.bakeoff_to_csv(report)
        self.assertIn("dimension,case_id,path,metric,value", csv_text)
        self.assertIn("filtering", csv_text)
        self.assertNotIn(",k2,", csv_text)  # no K2 rows when unconfigured
        markdown = bakeoff.bakeoff_to_markdown(report)
        self.assertIn("# K2 vs local bake-off", markdown)
        self.assertIn("K2 not configured", markdown)

    def test_seeded_run_category_label_is_populated(self) -> None:
        labels = bakeoff.category_by_domain(seeded_run())
        self.assertGreater(len(labels), 400)
        self.assertTrue(any(category for category in labels.values()))


if __name__ == "__main__":
    unittest.main()
