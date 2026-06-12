from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from icp_engine.app_store import AppStore


class AppStoreTest(unittest.TestCase):
    def test_criteria_defaults_to_icp_path_and_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            icp_path = root / "icp.md"
            icp_path.write_text("# Original ICP\n", encoding="utf-8")
            store = AppStore(root / "state", icp_path)

            self.assertEqual(store.load_criteria()["markdown"], "# Original ICP\n")
            updated = store.save_criteria("# New ICP\n\n- Gate")

            self.assertEqual(updated["markdown"], "# New ICP\n\n- Gate\n")
            self.assertTrue((root / "state" / "criteria.md").exists())

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

