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
