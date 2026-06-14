from __future__ import annotations

import unittest

from icp_engine.outreach import build_lead_outreach_drafts


class OutreachDraftTest(unittest.TestCase):
    def test_uses_cached_personalized_copy_when_present(self) -> None:
        run = _run()
        run["leads"][0]["metadata"]["outreach_messages"] = {
            "economic_buyer": {
                "subject": "Mojio's telematics data as an AI wedge",
                "body": "Hi — your connected-vehicle data is a real AI asset.",
                "cta": "Open to a 20-minute look?",
                "angle": "Anchored to their telematics data moat.",
                "role": "economic_buyer",
                "title": "Chief Product Officer",
                "grounded": "k2",
            }
        }

        drafts = build_lead_outreach_drafts(run, run["leads"][0])
        cpo = _draft_for_persona(drafts, "Chief Product Officer")
        vpe = _draft_for_persona(drafts, "VP Engineering")

        self.assertEqual(cpo["subject"], "Mojio's telematics data as an AI wedge")
        self.assertIn("connected-vehicle data", cpo["body"])
        self.assertEqual(cpo["cta"], "Open to a 20-minute look?")
        self.assertTrue(cpo["personalized"])
        self.assertEqual(cpo["grounded"], "k2")
        # No cached copy for the engineering persona -> template fallback.
        self.assertFalse(vpe["personalized"])
        self.assertEqual(vpe["subject"], "Mojio AI workflow opportunity map")

    def test_template_output_is_byte_for_byte_without_cache(self) -> None:
        run = _run()
        baseline = build_lead_outreach_drafts(run, run["leads"][0])

        run["leads"][0]["metadata"]["outreach_messages"] = {}
        with_empty_cache = build_lead_outreach_drafts(run, run["leads"][0])

        for before, after in zip(baseline, with_empty_cache):
            self.assertEqual(before["subject"], after["subject"])
            self.assertEqual(before["body"], after["body"])
            self.assertEqual(before["cta"], after["cta"])
            self.assertFalse(after["personalized"])


def _draft_for_persona(drafts: list[dict[str, object]], persona: str) -> dict[str, object]:
    for draft in drafts:
        if draft.get("persona") == persona:
            return draft
    raise AssertionError(f"no draft for persona {persona!r}")


def _run() -> dict[str, object]:
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
                    "company": {"company": "Mojio", "domain": "moj.io"},
                },
                "strategy": {
                    "outreach_angle": "Workflow data can become a product advantage.",
                    "offer": "Propose a 2-week AI opportunity map.",
                    "first_step": "Validate product ownership.",
                    "personas": [
                        {
                            "title": "Chief Product Officer",
                            "priority": "primary",
                            "apollo_titles": ["chief product officer", "vp product"],
                        },
                        {
                            "title": "VP Engineering",
                            "priority": "primary",
                            "apollo_titles": ["vp engineering", "head of engineering"],
                        },
                    ],
                    "committee": [
                        {"role": "economic_buyer", "title": "Chief Product Officer"},
                        {"role": "technical_evaluator", "title": "VP Engineering"},
                    ],
                },
                "metadata": {},
                "evidence": [
                    {
                        "title": "Mojio Platform",
                        "url": "https://moj.io/platform",
                        "text": "Connected vehicle data platform with APIs and analytics.",
                    }
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
