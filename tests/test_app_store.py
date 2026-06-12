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


if __name__ == "__main__":
    unittest.main()
