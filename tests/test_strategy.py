from __future__ import annotations

import unittest

from icp_engine.models import CompanyInput, Evidence
from icp_engine.scoring import score_company
from icp_engine.strategy import build_strategy


class StrategyTest(unittest.TestCase):
    def test_strategy_recommends_personas_and_outreach_angle(self) -> None:
        company = CompanyInput(company="FleetOps", domain="fleetops.example", category="fleet software", employee_count=250)
        evidence = [
            Evidence(
                evidence_id="e1",
                url="https://fleetops.example/platform",
                title="Fleet Platform",
                text="Founded in 2011. Enterprise fleet software with workflow, dispatch, API, integrations, analytics, and permissions.",
            )
        ]
        score = score_company(company, evidence)

        strategy = build_strategy(score, evidence)

        self.assertIn("outreach_angle", strategy)
        self.assertTrue(strategy["personas"])
        self.assertIn("vp product", strategy["apollo_titles"])


if __name__ == "__main__":
    unittest.main()

