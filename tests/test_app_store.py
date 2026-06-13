from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from icp_engine.app_store import AppStore


class AppStoreTest(unittest.TestCase):
    def test_empty_state_exposes_seeded_prompts_settings_lists_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp) / "state", Path(tmp) / "missing-icp.md")

            state = store.state()

            self.assertIn("Seeded ICP Criteria", state["criteria"]["markdown"])
            self.assertEqual(state["settings"]["deployment_mode"], "cloudflare-seeded-worker")
            self.assertGreaterEqual(len(state["prompts"]), 1)
            self.assertGreaterEqual(len(state["lists"]["account_universe"]), 428)
            companies = {item["company"] for item in state["lists"]["account_universe"]}
            self.assertIn("Mojio", companies)
            self.assertIn("Automate", companies)
            self.assertIn("Advanced Utility Systems", companies)
            self.assertIn("Symplicity", companies)
            self.assertIn("ServiceTitan", companies)
            self.assertEqual(state["latest_run"]["id"], "run-seeded-icp")
            self.assertGreaterEqual(len(state["latest_run"]["leads"]), 428)
            self.assertEqual(state["latest_run"]["leads"][0]["score"]["company"]["company"], "ServiceTitan")
            self.assertEqual(state["latest_run"]["leads"][0]["score"]["total_score"], 86)
            self.assertEqual(state["latest_run"]["leads"][0]["metadata"]["qualification"]["classification_source"], "rules")
            self.assertGreaterEqual(len(state["sources"]), 3)
            self.assertGreaterEqual(state["source_coverage"]["source_count"], 3)

    def test_criteria_defaults_to_icp_path_and_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            icp_path = root / "icp.md"
            icp_path.write_text("# Original ICP\n", encoding="utf-8")
            store = AppStore(root / "state", icp_path)

            original = store.load_criteria()
            self.assertEqual(original["markdown"], "# Original ICP\n")
            updated = store.save_criteria("# New ICP  \n\n* Gate\t")

            self.assertEqual(updated["markdown"], "# New ICP\n\n- Gate\n")
            self.assertTrue((root / "state" / "criteria.md").exists())
            versions = store.list_criteria_versions()
            version_hashes = {item["hash"] for item in versions}
            self.assertIn(original["hash"], version_hashes)
            self.assertIn(updated["hash"], version_hashes)

            lint = store.lint_criteria("# ICP  \n* Gate")
            self.assertTrue(lint["changed"])
            self.assertGreaterEqual(lint["warning_count"], 1)

            restored = store.restore_criteria_version(original["hash"])
            self.assertIsNotNone(restored)
            self.assertEqual(restored["markdown"], "# Original ICP\n")

    def test_save_run_updates_index_and_loads_latest_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            run = {
                "id": "run-123",
                "query": "fleet software",
                "created_at": "2026-06-11T00:00:00+00:00",
                "status": "completed",
                "warnings": [],
                "leads": [
                    {
                        "score": {
                            "tier": "A",
                            "total_score": 81,
                        }
                    }
                ],
            }

            store.save_run(run)

            self.assertEqual(store.load_run("run-123")["query"], "fleet software")
            self.assertEqual(store.list_runs()[0]["top_score"], 81)
            self.assertEqual(store.state()["latest_run"]["id"], "run-123")

    def test_lead_workflow_state_views_and_audit_log_are_durable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            run = {
                "id": "run-workflow",
                "query": "fleet software",
                "created_at": "2026-06-11T00:00:00+00:00",
                "status": "completed",
                "warnings": [],
                "leads": [
                    {
                        "score": {
                            "company": {"company": "Mojio", "domain": "moj.io"},
                            "tier": "A",
                            "total_score": 82,
                        }
                    },
                    {
                        "score": {
                            "company": {"company": "Fleetio", "domain": "fleetio.com"},
                            "tier": "C",
                            "total_score": 47,
                        }
                    },
                ],
            }
            store.save_run(run)

            mojio = store.save_lead_state(
                "run-workflow",
                "https://www.moj.io/platform",
                company="Mojio",
                status="qualified",
                note="High-fit fleet data workflow.",
                owner="Anton",
                tags=["fleet", "tier-a", "fleet"],
            )
            bulk = store.bulk_update_lead_states(
                "run-workflow",
                ["fleetio.com"],
                status="rejected",
                note="Below threshold",
            )
            view = store.save_lead_view(
                "Tier A Review",
                filters={"status": ["Qualified"], "tier": ["A"]},
                sort={"field": "score", "direction": "desc"},
                page_size=25,
            )

            reloaded = AppStore(Path(tmp))
            hydrated = reloaded.load_run("run-workflow")

            self.assertEqual(mojio["domain"], "moj.io")
            self.assertEqual(mojio["status"], "Qualified")
            self.assertEqual(mojio["tags"], ["fleet", "tier-a"])
            self.assertEqual(bulk["updated_count"], 1)
            self.assertEqual(view["name"], "Tier A Review")
            self.assertEqual(hydrated["workflow"]["status_counts"]["Qualified"], 1)
            self.assertEqual(hydrated["workflow"]["status_counts"]["Rejected"], 1)
            self.assertEqual(hydrated["leads"][0]["workflow"]["status"], "Qualified")
            self.assertEqual(reloaded.state()["runs"][0]["lead_status_counts"]["Rejected"], 1)
            self.assertGreaterEqual(len(reloaded.list_audit_events()), 3)

            with self.assertRaises(ValueError):
                reloaded.save_lead_state("run-workflow", "moj.io", status="not-a-status")

    def test_account_detail_combines_workflow_prospects_evidence_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            run = {
                "id": "run-account",
                "query": "fleet software",
                "created_at": "2026-06-11T00:00:00+00:00",
                "status": "completed",
                "criteria": {
                    "hash": "criteria123",
                    "profile": {
                        "tier_a_threshold": 75,
                        "tier_b_threshold": 60,
                        "priority_terms": ["workflow", "fleet"],
                    },
                },
                "leads": [
                    {
                        "id": "lead-mojio",
                        "score": {
                            "company": {"company": "Mojio", "domain": "moj.io"},
                            "tier": "A",
                            "total_score": 82,
                            "gates": [],
                        },
                        "strategy": {
                            "outreach_angle": "Workflow AI opportunity map.",
                            "first_step": "Send VP Engineering brief.",
                            "personas": [
                                {"title": "VP Engineering", "priority": "primary"},
                                {"title": "VP Product", "priority": "secondary"},
                            ],
                        },
                        "metadata": {
                            "source_counts": {"website": 1},
                            "source_refs": {"linkedin_urls": ["https://www.linkedin.com/company/mojio"]},
                            "intelligence_coverage": {"linkedin": True},
                        },
                        "evidence": [
                            {
                                "evidence_id": "e1",
                                "url": "https://moj.io/platform",
                                "title": "Platform",
                                "text": "Fleet workflow API evidence.",
                                "metadata": {"page_category": "product"},
                            }
                        ],
                    }
                ],
            }
            store.save_run(run)
            store.save_lead_state("run-account", "https://www.moj.io/platform", company="Mojio", status="Qualified", note="Ready.")

            detail = store.account_detail("run-account", "moj.io")

            self.assertIsNotNone(detail)
            assert detail is not None
            self.assertEqual(detail["company"]["company"], "Mojio")
            self.assertEqual(detail["workflow"]["status"], "Qualified")
            self.assertEqual(detail["criteria_snapshot"]["hash"], "criteria123")
            self.assertEqual(detail["role_groups"][0]["role"], "VP Engineering")
            self.assertEqual(detail["prospects"][0]["status"], "persona_target")
            self.assertEqual(detail["evidence_timeline"][0]["title"], "Platform")
            self.assertEqual(detail["source_counts"]["website"], 1)
            self.assertIn("lead_state.updated", {item["action"] for item in detail["audit_events"]})
            self.assertIsNone(store.account_detail("run-account", "missing.example"))

    def test_sources_and_scan_history_are_durable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))

            source = store.save_source(
                "Constellation search",
                source_type="serp_query",
                value="constellation software portfolio workflow companies",
                source_group="portfolio-expansion",
                schedule="weekly",
            )
            scan = store.record_source_scan(
                source["id"],
                status="completed",
                candidates=[
                    {
                        "company": "Mojio",
                        "domain": "moj.io",
                        "source_url": "https://moj.io",
                        "source_title": "Mojio",
                        "notes": "Fleet workflow software.",
                    }
                ],
                warnings=["one warning"],
            )

            reloaded = AppStore(Path(tmp))
            sources = reloaded.load_sources()
            coverage = reloaded.source_coverage()

            self.assertEqual(scan["candidate_count"], 1)
            self.assertTrue(any(item["id"] == source["id"] and item["last_candidate_count"] == 1 for item in sources))
            self.assertEqual(reloaded.list_source_scans(source_id=source["id"])[0]["candidates"][0]["domain"], "moj.io")
            self.assertGreaterEqual(coverage["source_count"], 3)
            self.assertEqual(coverage["unique_candidate_domains"], 1)

            with self.assertRaises(ValueError):
                reloaded.save_source("Bad", source_type="bad", value="x")


if __name__ == "__main__":
    unittest.main()
