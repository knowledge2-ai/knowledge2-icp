from __future__ import annotations

import unittest

from icp_engine.prospects import build_run_prospects, prospects_to_csv


class ProspectsTest(unittest.TestCase):
    def test_builds_apollo_people_prospects_and_csv(self) -> None:
        run = _run(
            metadata={
                "apollo_people": {
                    "status": "ok",
                    "people": [
                        {
                            "id": "person-1",
                            "name": "Jane Doe",
                            "title": "VP Product",
                            "email": "jane@example.com",
                            "linkedin_url": "https://linkedin.com/in/jane",
                            "city": "Vancouver",
                            "country": "Canada",
                            "organization": {"name": "Mojio"},
                        }
                    ],
                }
            }
        )

        payload = build_run_prospects(run)

        self.assertEqual(payload["prospect_count"], 1)
        self.assertEqual(payload["source_counts"], {"apollo": 1})
        prospect = payload["prospects"][0]
        self.assertEqual(prospect["source"], "apollo")
        self.assertEqual(prospect["name"], "Jane Doe")
        self.assertEqual(prospect["persona"], "Chief Product Officer")
        self.assertGreater(prospect["priority_score"], 100)

        csv_text = prospects_to_csv(payload)
        self.assertIn("Jane Doe", csv_text)
        self.assertIn("jane@example.com", csv_text)

    def test_falls_back_to_strategy_personas_without_people(self) -> None:
        payload = build_run_prospects(_run(metadata={}))

        self.assertEqual(payload["prospect_count"], 2)
        self.assertEqual(payload["source_counts"], {"strategy": 2})
        titles = {item["title"] for item in payload["prospects"]}
        self.assertEqual(titles, {"Chief Product Officer", "VP Engineering"})

    def test_surfaces_committee_role_on_matching_prospect(self) -> None:
        run = _run(metadata={})
        run["leads"][0]["strategy"]["committee"] = [
            {"role": "economic_buyer", "title": "Chief Product Officer"},
            {"role": "technical_evaluator", "title": "VP Engineering"},
        ]

        payload = build_run_prospects(run)

        roles = {item["title"]: item["committee_role"] for item in payload["prospects"]}
        self.assertEqual(roles["Chief Product Officer"], "economic_buyer")
        self.assertEqual(roles["VP Engineering"], "technical_evaluator")
        self.assertIn("committee_role", prospects_to_csv(payload).splitlines()[0])

    def test_committee_role_blank_without_committee(self) -> None:
        payload = build_run_prospects(_run(metadata={}))
        self.assertTrue(all(item["committee_role"] == "" for item in payload["prospects"]))


def _run(*, metadata: dict[str, object]) -> dict[str, object]:
    return {
        "id": "run-test",
        "query": "test",
        "criteria": {"hash": "abc"},
        "leads": [
            {
                "id": "lead-1",
                "score": {
                    "tier": "A",
                    "total_score": 82,
                    "company": {
                        "company": "Mojio",
                        "domain": "moj.io",
                    },
                },
                "strategy": {
                    "outreach_angle": "Workflow data can become a product advantage.",
                    "first_step": "Validate product ownership.",
                    "personas": [
                        {
                            "title": "Chief Product Officer",
                            "priority": "primary",
                            "apollo_titles": ["chief product officer", "vp product", "head of product"],
                        },
                        {
                            "title": "VP Engineering",
                            "priority": "primary",
                            "apollo_titles": ["vp engineering", "head of engineering"],
                        },
                    ],
                },
                "metadata": metadata,
                "evidence": [],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
