from __future__ import annotations

import unittest

from icp_engine.discovery import parse_seed_companies
from icp_engine.models import CompanyInput, Evidence
from icp_engine.scoring import _ai_gap_points, score_company
from icp_engine.seed_defaults import seeded_run
from icp_engine.serialization import score_to_dict

COMPONENT_KEYS = {
    "ai_gap_score",
    "data_workflow_score",
    "commercial_urgency_score",
    "budget_access_score",
    "feasibility_score",
}
REASON_COMPONENT_KEYS = {
    "ai_posture",
    "data_workflow",
    "commercial_urgency",
    "budget_access",
    "feasibility",
}


class SeededLeadQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.seed_run = seeded_run()
        cls.leads = cls.seed_run["leads"]

    def test_run_has_qualifier_and_discovery(self) -> None:
        self.assertIn("qualifier", self.seed_run)
        self.assertIn("discovery", self.seed_run)
        self.assertEqual(self.seed_run["qualifier"], "rules")
        self.assertIn("provider", self.seed_run["discovery"])

    def test_total_score_equals_sum_of_components(self) -> None:
        for lead in self.leads:
            score = lead["score"]
            component_sum = sum(score[key] for key in COMPONENT_KEYS)
            self.assertEqual(
                score["total_score"],
                component_sum,
                msg=f"{score['company']['company']} total != sum of components",
            )

    def test_ai_gap_score_matches_live_mapping(self) -> None:
        for lead in self.leads:
            score = lead["score"]
            self.assertEqual(
                score["ai_gap_score"],
                _ai_gap_points(score["classification"]["ai_posture"]),
                msg=f"{score['company']['company']} ai_gap_score diverges from mapping",
            )

    def test_ai_narrative_present(self) -> None:
        for lead in self.leads:
            self.assertIn("ai_narrative", lead["score"])

    def test_hard_gate_flags_derive_from_gates(self) -> None:
        for lead in self.leads:
            score = lead["score"]
            gates = score["gates"]
            self.assertEqual(
                score["hard_gate_unknown"],
                any(gate["status"] == "unknown" for gate in gates),
                msg=f"{score['company']['company']} hard_gate_unknown diverges from gates",
            )
            self.assertEqual(
                score["hard_gate_failed"],
                any(gate["status"] == "fail" for gate in gates),
                msg=f"{score['company']['company']} hard_gate_failed diverges from gates",
            )

    def test_tier_consistency_with_score_and_gates(self) -> None:
        for lead in self.leads:
            score = lead["score"]
            total = score["total_score"]
            if any(gate["status"] == "fail" for gate in score["gates"]):
                self.assertEqual(score["tier"], "Reject")
                continue
            if total >= 75:
                expected = "A"
            elif total >= 60:
                expected = "B"
            else:
                expected = "C"
            self.assertEqual(
                score["tier"],
                expected,
                msg=f"{score['company']['company']} tier {score['tier']} != {expected} for total {total}",
            )

    def test_committee_present_and_shaped(self) -> None:
        for lead in self.leads:
            committee = lead["strategy"].get("committee")
            self.assertIsInstance(committee, list, msg=f"{lead['id']} committee missing or not a list")
            if lead["score"]["tier"] != "Reject":
                self.assertTrue(committee, msg=f"{lead['id']} committee empty for non-Reject lead")

    def test_qualification_reasons_carry_five_component_keys(self) -> None:
        for lead in self.leads:
            reasons = lead["metadata"]["qualification"]["reasons"]
            self.assertTrue(
                REASON_COMPONENT_KEYS <= set(reasons),
                msg=f"{lead['id']} qualification reasons missing component keys: {set(reasons)}",
            )

    def test_score_dict_schema_parity_with_serialization(self) -> None:
        real = score_to_dict(
            score_company(
                CompanyInput("Example", "example.com", category="software platform"),
                [Evidence("e1", "https://example.com", "Example", "workflow platform software")],
            )
        )
        expected_keys = set(real)
        for lead in self.leads:
            self.assertEqual(
                set(lead["score"]),
                expected_keys,
                msg=f"{lead['id']} score keys diverge from serialization.score_to_dict",
            )


class ParseSeedCompaniesTests(unittest.TestCase):
    def test_comma_list_of_domains_is_split(self) -> None:
        candidates = parse_seed_companies("moj.io, automate.co.za")
        self.assertEqual(len(candidates), 2)
        self.assertEqual({c.domain for c in candidates}, {"moj.io", "automate.co.za"})

    def test_name_domain_form_preserved(self) -> None:
        candidates = parse_seed_companies("Mojio, moj.io")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].domain, "moj.io")
        self.assertEqual(candidates[0].company, "Mojio")

    def test_multiline_name_domain_parses_per_line(self) -> None:
        candidates = parse_seed_companies("Acme, acme.com\nBeta Corp, beta.io")
        self.assertEqual(len(candidates), 2)
        self.assertEqual([c.domain for c in candidates], ["acme.com", "beta.io"])
        self.assertEqual(candidates[0].company, "Acme")
        self.assertEqual(candidates[1].company, "Beta Corp")

    def test_header_and_comment_skipped(self) -> None:
        candidates = parse_seed_companies("# header line\nCompany, Domain\nAcme, acme.com")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].domain, "acme.com")


if __name__ == "__main__":
    unittest.main()
