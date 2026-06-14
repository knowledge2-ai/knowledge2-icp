from __future__ import annotations

import unittest

from icp_engine.mining import (
    lookalikes_local,
    mine_local,
    mining_to_csv,
    normalize_clauses,
)


class _FakeStore:
    """Minimal store exposing the run-loading API mine_local depends on."""

    def __init__(self, runs: list[dict[str, object]]) -> None:
        self._runs = runs

    def list_runs(self) -> list[dict[str, object]]:
        return [{"id": run["id"]} for run in self._runs]

    def load_run(self, run_id: str) -> dict[str, object] | None:
        return next((run for run in self._runs if run["id"] == run_id), None)


def _lead(company: str, domain: str, *, tier: str, posture: str, vertical: str, score: int) -> dict[str, object]:
    return {
        "score": {
            "tier": tier,
            "total_score": score,
            "company": {"company": company, "domain": domain},
            "classification": {"ai_posture": posture},
        },
        "metadata": {"vertical": vertical},
        "strategy": {"outreach_angle": f"{company} workflow data wedge"},
        "evidence": [{"url": f"https://{domain}/about", "text": f"{company} platform"}],
        "workflow": {"status": "new"},
    }


def _store() -> _FakeStore:
    return _FakeStore(
        [
            {
                "id": "run-1",
                "leads": [
                    _lead("Mojio", "moj.io", tier="A", posture="none", vertical="telematics", score=82),
                    _lead("FleetCo", "fleetco.com", tier="A", posture="none", vertical="telematics", score=78),
                    _lead("WidgetCorp", "widget.com", tier="C", posture="ai-native", vertical="martech", score=40),
                ],
            }
        ]
    )


class MineLocalTest(unittest.TestCase):
    def test_filters_narrow_results_offline(self) -> None:
        payload = mine_local(_store(), query="", clauses=[("tier", "==", "A")], top_k=20)

        self.assertEqual(payload["provider"], "local")
        domains = {result["domain"] for result in payload["results"]}
        self.assertEqual(domains, {"moj.io", "fleetco.com"})
        self.assertEqual(payload["facets"]["tier"], {"A": 2})
        self.assertTrue(any("in-memory" in warning for warning in payload["warnings"]))

    def test_unevaluable_filter_key_is_warned_not_fatal(self) -> None:
        payload = mine_local(_store(), query="", clauses=[("feed_id", "==", "x")], top_k=20)

        self.assertEqual(len(payload["results"]), 3)  # feed_id not evaluable offline -> not applied
        self.assertTrue(any("feed_id" in warning for warning in payload["warnings"]))

    def test_query_tokens_rank_relevant_leads_first(self) -> None:
        payload = mine_local(_store(), query="telematics", clauses=[], top_k=20)
        self.assertEqual(payload["results"][0]["vertical"], "telematics")

    def test_empty_store_does_not_raise(self) -> None:
        payload = mine_local(_FakeStore([]), query="anything", clauses=[("tier", "==", "A")], top_k=20)
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["facets"], {"tier": {}, "ai_posture": {}, "vertical": {}})


class MatchOperatorsTest(unittest.TestCase):
    """Exercise every clause operator through the offline mine, not just ``==``."""

    def _domains(self, key: str, op: str, value: object) -> set[str]:
        payload = mine_local(_store(), query="", clauses=[(key, op, value)], top_k=20)
        return {result["domain"] for result in payload["results"]}

    def test_numeric_comparisons(self) -> None:
        self.assertEqual(self._domains("total_score", ">", 70), {"moj.io", "fleetco.com"})
        self.assertEqual(self._domains("total_score", ">=", 78), {"moj.io", "fleetco.com"})
        self.assertEqual(self._domains("total_score", "<", 50), {"widget.com"})
        self.assertEqual(self._domains("total_score", "<=", 78), {"fleetco.com", "widget.com"})

    def test_not_equal(self) -> None:
        self.assertEqual(self._domains("tier", "!=", "A"), {"widget.com"})

    def test_in_and_contains(self) -> None:
        self.assertEqual(self._domains("vertical", "in", ["telematics"]), {"moj.io", "fleetco.com"})
        self.assertEqual(self._domains("vertical", "contains", "tele"), {"moj.io", "fleetco.com"})

    def test_comparison_on_non_numeric_field_is_false_not_string_equality(self) -> None:
        # A non-numeric operand can't be ordered; a `>` clause must not degrade to `==`.
        self.assertEqual(self._domains("tier", ">", "A"), set())


class LookalikesLocalTest(unittest.TestCase):
    def test_excludes_seed_and_ranks_by_shared_features(self) -> None:
        payload = lookalikes_local(_store(), seed_domains=["moj.io"], top_k=20)

        domains = [result["domain"] for result in payload["results"]]
        self.assertNotIn("moj.io", domains)
        self.assertEqual(domains[0], "fleetco.com")  # shares vertical + posture + tier band
        self.assertNotIn("widget.com", domains)  # no shared features -> dropped

    def test_empty_seeds_returns_warning(self) -> None:
        payload = lookalikes_local(_store(), seed_domains=[], top_k=20)
        self.assertEqual(payload["results"], [])
        self.assertTrue(payload["warnings"])


class HelpersTest(unittest.TestCase):
    def test_normalize_clauses_accepts_dicts_and_tuples(self) -> None:
        clauses = normalize_clauses([{"key": "tier", "op": "==", "value": "A"}, ("ai_posture", "==", "none")])
        self.assertEqual(clauses, [("tier", "==", "A"), ("ai_posture", "==", "none")])

    def test_csv_has_header_and_rows(self) -> None:
        payload = mine_local(_store(), query="", clauses=[("tier", "==", "A")], top_k=20)
        csv_text = mining_to_csv(payload)
        self.assertIn("company,domain,vertical,tier,ai_posture", csv_text.splitlines()[0])
        self.assertIn("moj.io", csv_text)


if __name__ == "__main__":
    unittest.main()
