from __future__ import annotations

import unittest

from icp_engine.criteria import build_criteria_profile
from icp_engine.models import CompanyInput, Evidence, GateStatus
from icp_engine.scoring import score_company


class CriteriaProfileTest(unittest.TestCase):
    def test_build_criteria_profile_parses_thresholds_budget_and_verticals(self) -> None:
        profile = build_criteria_profile(
            """
            # ICP
            Tier A threshold: 88
            Tier B threshold: 70
            Budget: 50-1000 employees
            Priority verticals: maritime, fleet, payments
            """,
            source="criteria.md",
            criteria_hash="abc123",
        )

        self.assertEqual(profile.hash, "abc123")
        self.assertEqual(profile.tier_a_threshold, 88)
        self.assertEqual(profile.tier_b_threshold, 70)
        self.assertEqual(profile.min_employee_count, 50)
        self.assertEqual(profile.max_employee_count, 1000)
        self.assertIn("maritime", profile.priority_terms)
        self.assertIn("fleet", profile.priority_terms)
        self.assertIn("payments", profile.priority_terms)

    def test_criteria_profile_changes_tier_thresholds(self) -> None:
        company = CompanyInput(company="FleetOps", domain="fleetops.example", category="fleet software", employee_count=250)
        evidence = [
            Evidence(
                "e1",
                "https://fleetops.example/platform",
                "Platform",
                (
                    "Founded in 2011. Enterprise fleet software platform for workflow, dispatch, "
                    "telematics records, integrations, API, permissions, analytics, reporting, "
                    "automation, efficiency, real-time predictive insights, and trusted customers."
                ),
            )
        ]
        strict_profile = build_criteria_profile("Tier A threshold: 95\nTier B threshold: 80\nBudget: 50-1000 employees")

        default_score = score_company(company, evidence)
        strict_score = score_company(company, evidence, criteria_profile=strict_profile)

        self.assertEqual(default_score.tier, "A")
        self.assertEqual(strict_score.total_score, default_score.total_score)
        self.assertEqual(strict_score.tier, "B")
        self.assertIn("Tier A >= 95", strict_score.classification.reasons["criteria"])

    def test_criteria_profile_changes_budget_gate_range(self) -> None:
        company = CompanyInput(company="SmallOps", domain="smallops.example", employee_count=30)
        evidence = [
            Evidence(
                "e1",
                "https://smallops.example/platform",
                "Platform",
                "Founded in 2011. B2B software platform with workflow, records, API, and analytics.",
            )
        ]
        profile = build_criteria_profile("Budget: 50-1000 employees")

        score = score_company(company, evidence, criteria_profile=profile)
        budget_gate = next(gate for gate in score.gates if gate.name == "Enough budget")

        self.assertEqual(budget_gate.status, GateStatus.UNKNOWN)
        self.assertIn("below active criteria minimum 50", budget_gate.reason)


if __name__ == "__main__":
    unittest.main()
