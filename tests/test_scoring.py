import unittest

from icp_engine.models import Classification, CompanyInput, Evidence
from icp_engine.scoring import score_company
from icp_engine.serialization import score_to_dict


class ScoringTests(unittest.TestCase):
    def test_tier_a_for_data_rich_low_ai_incumbent(self):
        company = CompanyInput(
            company="Mojio Like",
            domain="example.com",
            category="fleet telematics",
            founded_year=2012,
            employee_count=120,
            notes="B2B platform for enterprise fleets.",
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Fleet platform",
                "Software platform for fleets with API integrations, trips, diagnostics, workflow, "
                "analytics, reporting, real-time telematics, customers, partners, cloud security.",
            )
        ]

        result = score_company(company, evidence)

        self.assertEqual(result.tier, "A")
        self.assertGreaterEqual(result.total_score, 75)
        self.assertEqual(result.classification.ai_posture, 0)
        self.assertFalse(result.hard_gate_failed)

    def test_vertical_focus_outweighs_horizontal_data_breadth(self):
        # Two AI-light, pre-2025, in-budget incumbents that are identical on every
        # signal except one: the first serves a target vertical, the second is a
        # horizontal data-rich platform. The ICP is "vertical software incumbents,
        # not broad SaaS," so the vertical company must score the deeper moat and
        # clearly outrank the horizontal one — not merely tie it.
        shared = "Real-time automation improves efficiency for enterprise customers."
        vertical = CompanyInput(
            company="Vertical VMS",
            domain="vertical.example.com",
            category="construction compliance software",
            founded_year=2008,
            employee_count=300,
        )
        vertical_evidence = [
            Evidence(
                "v1",
                "https://vertical.example.com",
                "Construction compliance",
                "Software platform for construction firms with compliance workflows, work "
                f"orders, inspections, documents, api integrations, analytics, reporting. {shared}",
            )
        ]
        horizontal = CompanyInput(
            company="Horizontal Fintech",
            domain="horizontal.example.com",
            category="accounts receivable automation",
            founded_year=2008,
            employee_count=300,
        )
        horizontal_evidence = [
            Evidence(
                "h1",
                "https://horizontal.example.com",
                "AR automation",
                "Software platform for businesses with payment workflows, transactions, "
                f"invoices, documents, api integrations, analytics, reporting. {shared}",
            )
        ]

        vertical_result = score_company(vertical, vertical_evidence)
        horizontal_result = score_company(horizontal, horizontal_evidence)

        self.assertGreater(vertical_result.data_workflow_score, horizontal_result.data_workflow_score)
        self.assertGreaterEqual(vertical_result.total_score, horizontal_result.total_score + 8)

    def test_ai_native_fails_hard_gate(self):
        company = CompanyInput(
            company="AI Native",
            domain="example.com",
            category="AI agents",
            founded_year=2025,
            employee_count=20,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "AI agents",
                "AI-native autonomous agent and generative AI platform for companies.",
            )
        ]

        result = score_company(company, evidence)

        self.assertEqual(result.tier, "Reject")
        self.assertTrue(result.hard_gate_failed)

    def test_frontier_ai_lab_rejected_on_single_strong_signal(self):
        # Regression: an AI lab whose pages carry frontier-lab category terms
        # ("ai safety", "frontier ai") but only one of the weaker AI_NATIVE
        # phrases used to slip the >=2 count and score a non-Reject tier, while a
        # near-identical lab that happened to hit two weak phrases was rejected.
        # A single strong signal must reject — the "Not AI-native" hard gate.
        company = CompanyInput(
            company="Frontier Lab",
            domain="example.com",
            category="AI research and products",
            founded_year=2021,
            employee_count=300,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Research",
                "We are an AI safety and research company building frontier AI systems. "
                "Our products include AI agents for businesses.",
            )
        ]

        result = score_company(company, evidence)

        self.assertEqual(result.tier, "Reject")
        self.assertTrue(result.hard_gate_failed)

    def test_horizontal_platform_with_no_vertical_fails_hard_gate(self):
        # The ICP is vertical incumbents, not broad SaaS. A pre-2025, in-budget,
        # data-rich product company that describes itself in purely horizontal
        # terms with no target-vertical signal (Stripe-style) must reject, not
        # land in a passing tier.
        company = CompanyInput(
            company="Horizontal Payments",
            domain="example.com",
            category="payments infrastructure",
            founded_year=2010,
            employee_count=1500,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Payments",
                "Payments software platform for businesses of all sizes, used by millions of "
                "businesses. Transactions, invoices, documents, api integrations, analytics.",
            )
        ]

        result = score_company(company, evidence)

        self.assertEqual(result.tier, "Reject")
        self.assertTrue(result.hard_gate_failed)

    def test_vertical_incumbent_with_stray_horizontal_phrase_not_rejected(self):
        # A clear target-vertical incumbent that also uses one breadth phrase
        # ("for everyone", as ServiceTitan/Procore do) must NOT trip the
        # horizontal gate — the target-vertical signal takes precedence.
        company = CompanyInput(
            company="Field Service Co",
            domain="example.com",
            category="field service management software",
            founded_year=2012,
            employee_count=900,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Field service",
                "Field service management software for everyone in the trades: dispatch, work "
                "orders, schedules, inspections, documents, api integrations, analytics.",
            )
        ]

        result = score_company(company, evidence)

        self.assertNotEqual(result.tier, "Reject")
        self.assertFalse(result.hard_gate_failed)

    def test_broad_saas_name_dropping_many_verticals_is_rejected(self):
        # The broad-SaaS leak: a horizontal platform (category is generic, not a
        # vertical) name-drops the many industries it serves. Scattered vertical
        # mentions must NOT confer a vertical anchor — naming >= 4 distinct
        # verticals with no anchor reads as horizontal and hard-fails the gate.
        company = CompanyInput(
            company="Broad Data Co",
            domain="example.com",
            category="financial data infrastructure",
            founded_year=2013,
            employee_count=1200,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Platform",
                "Data platform serving insurance, healthcare, banking, legal, and retail teams. "
                "Proprietary data, recurring workflow, API integrations, analytics, dashboards.",
            )
        ]

        result = score_company(company, evidence)

        self.assertEqual(result.tier, "Reject")
        self.assertTrue(result.hard_gate_failed)

    def test_non_anchored_strong_scorer_capped_at_tier_c(self):
        # A non-anchored product company that passes every hard gate and scores
        # well (low AI, data-rich, feasible) must still be capped at Tier C, not
        # pursued as A/B — Tier A/B is reserved for vertical incumbents. No strong
        # horizontal phrasing here, so it is deprioritized, not rejected.
        company = CompanyInput(
            company="Generic Workflow Co",
            domain="example.com",
            category="workflow automation software",
            founded_year=2012,
            employee_count=400,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Platform",
                "B2B software platform with proprietary data, recurring workflow, dispatch, work "
                "orders, schedules, documents, API integrations, analytics, reporting, trusted by "
                "thousands of customers, cloud security, permissions, SSO.",
            )
        ]

        result = score_company(company, evidence)

        self.assertEqual(result.tier, "C")
        self.assertFalse(result.hard_gate_failed)

    def test_anchored_incumbent_with_stray_other_vertical_mentions_stays_fit(self):
        # A category-anchored vertical incumbent (banking) that mentions adjacent
        # verticals in passing must remain anchored — the category anchor wins, so
        # it is not penalized as horizontal.
        company = CompanyInput(
            company="Bank Core Co",
            domain="example.com",
            category="banking software",
            founded_year=2011,
            employee_count=800,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Banking",
                "Cloud banking platform for banks and credit unions: lending, deposits, compliance, "
                "proprietary data, recurring workflow, API integrations, analytics, also used by "
                "insurance partners.",
            )
        ]

        result = score_company(company, evidence)

        self.assertNotEqual(result.tier, "Reject")
        self.assertFalse(result.hard_gate_failed)

    def test_unknown_founding_year_creates_review_flag_not_pass(self):
        company = CompanyInput(
            company="Unknown Co",
            domain="example.com",
            category="field service",
            employee_count=100,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Field service",
                "B2B software platform for field service workflow, dispatch, work orders, API integrations.",
            )
        ]

        result = score_company(company, evidence)

        self.assertTrue(result.hard_gate_unknown)
        self.assertTrue(any("Founded before 2025" in warning for warning in result.warnings))

    def test_model_reasons_do_not_leak_conflicting_rules_reasons(self):
        company = CompanyInput(
            company="Model Co",
            domain="example.com",
            category="field service",
            founded_year=2010,
            employee_count=100,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Field service",
                "B2B software platform with AI-powered workflow, dispatch, work orders, and API integrations.",
            )
        ]
        model = Classification(
            ai_posture=0,
            data_workflow=4,
            commercial_urgency=3,
            budget_access=3,
            feasibility=3,
            reasons={},
            confidence=0.8,
            source="gemini:test",
        )

        result = score_company(company, evidence, model_classification=model)

        self.assertEqual(result.classification.ai_posture, 0)
        self.assertIn("scored 0/5 by gemini:test", result.classification.reasons["ai_posture"])
        self.assertNotIn("AI-powered", result.classification.reasons["ai_posture"])

    def test_ai_narrative_defaults_empty_without_a_model(self):
        company = CompanyInput(
            company="Mojio Like",
            domain="example.com",
            category="fleet telematics",
            founded_year=2012,
            employee_count=120,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Fleet platform",
                "Software platform for fleets with API integrations, workflow, and analytics.",
            )
        ]

        result = score_company(company, evidence)

        self.assertEqual(result.ai_narrative, "")
        self.assertEqual(score_to_dict(result)["ai_narrative"], "")

    def test_ai_narrative_round_trips_from_model_classification(self):
        company = CompanyInput(
            company="Model Co",
            domain="example.com",
            category="field service",
            founded_year=2010,
            employee_count=100,
        )
        evidence = [
            Evidence(
                "e1",
                "https://example.com",
                "Field service",
                "B2B software platform with workflow, dispatch, work orders, and API integrations.",
            )
        ]
        model = Classification(
            ai_posture=3,
            data_workflow=4,
            commercial_urgency=3,
            budget_access=3,
            feasibility=3,
            reasons={},
            confidence=0.8,
            source="claude:test",
            ai_narrative="Builds an embedded dispatch assistant on proprietary fleet data.",
        )

        result = score_company(company, evidence, model_classification=model)

        self.assertEqual(result.ai_narrative, "Builds an embedded dispatch assistant on proprietary fleet data.")
        self.assertEqual(
            score_to_dict(result)["ai_narrative"],
            "Builds an embedded dispatch assistant on proprietary fleet data.",
        )


if __name__ == "__main__":
    unittest.main()
