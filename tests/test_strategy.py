from __future__ import annotations

import unittest

from icp_engine.models import CompanyInput, Evidence
from icp_engine.scoring import score_company
from icp_engine.strategy import COMMITTEE_ROLES, build_buying_committee, build_strategy


def _scored_company():
    company = CompanyInput(company="FleetOps", domain="fleetops.example", category="fleet software", employee_count=250)
    evidence = [
        Evidence(
            evidence_id="e1",
            url="https://fleetops.example/platform",
            title="Fleet Platform",
            text="Founded in 2011. Enterprise fleet software with workflow, dispatch, API, integrations, analytics, and permissions.",
        )
    ]
    return score_company(company, evidence), evidence


class StrategyTest(unittest.TestCase):
    def test_strategy_recommends_personas_and_outreach_angle(self) -> None:
        score, evidence = _scored_company()

        strategy = build_strategy(score, evidence)

        self.assertIn("outreach_angle", strategy)
        self.assertTrue(strategy["personas"])
        self.assertIn("vp product", strategy["apollo_titles"])

    def test_strategy_includes_structured_committee(self) -> None:
        score, evidence = _scored_company()

        strategy = build_strategy(score, evidence)
        committee = strategy["committee"]

        self.assertTrue(committee)
        roles = {role["role"] for role in committee}
        # Always at least an economic buyer and a champion to write to.
        self.assertIn("economic_buyer", roles)
        self.assertIn("champion", roles)
        self.assertTrue(roles.issubset(set(COMMITTEE_ROLES)))
        for role in committee:
            self.assertTrue(role["title"])
            self.assertTrue(role["apollo_titles"])
            self.assertTrue(role["angle"])

    def test_committee_is_empty_without_personas(self) -> None:
        score, _ = _scored_company()
        self.assertEqual(build_buying_committee(score, []), [])


if __name__ == "__main__":
    unittest.main()
