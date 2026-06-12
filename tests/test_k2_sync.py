from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from icp_engine.app_store import AppStore
from icp_engine.k2_backend import K2Backend
from icp_engine.k2_sync import main


class FakeK2Client:
    def __init__(self) -> None:
        self.uploaded = []

    def ensure_project(self, name: str) -> dict[str, str]:
        return {"id": "project-1", "name": name}

    def ensure_corpus(self, project_id: str, name: str, description: str = "") -> dict[str, str]:
        return {"id": "corpus-1", "name": name, "projectId": project_id}

    def upload_documents(self, corpus_id: str, documents: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
        self.uploaded.append((corpus_id, documents, kwargs))
        return {"jobId": "job-1", "batchId": "batch-1", "count": len(documents)}

    def generate_answer(self, corpus_id: str, query: str, **kwargs: object) -> dict[str, object]:
        return {
            "answer": "Mojio has fleet workflow API evidence.",
            "model": "k2-test",
            "results": [
                {
                    "text": "Fleet workflow API platform.",
                    "score": 0.91,
                    "customMetadata": {
                        "company": "Mojio",
                        "domain": "moj.io",
                        "source_url": "https://moj.io/platform",
                        "evidence_id": "e1",
                        "source_type": "website",
                        "page_category": "product",
                    },
                }
            ],
        }


def sample_run() -> dict[str, object]:
    return {
        "id": "run-test",
        "query": "fleet",
        "criteria": {"hash": "abc"},
        "leads": [
            {
                "score": {
                    "company": {"company": "Mojio", "domain": "moj.io"},
                    "tier": "A",
                    "total_score": 81,
                    "classification": {"ai_posture": 0},
                },
                "strategy": {
                    "personas": [{"title": "VP Product"}],
                    "outreach_angle": "Workflow AI gap.",
                },
                "metadata": {
                    "signal_tags": ["workflow"],
                    "public_profile_count": 2,
                    "public_resource_count": 2,
                    "source_refs": {
                        "github_urls": ["https://github.com/mojio"],
                        "linkedin_urls": ["https://www.linkedin.com/company/mojio"],
                        "social_urls": ["https://x.com/mojio"],
                        "marketplace_urls": ["https://www.crunchbase.com/organization/mojio"],
                    },
                },
                "evidence": [
                    {
                        "evidence_id": "e1",
                        "url": "https://moj.io/platform",
                        "title": "Platform",
                        "text": "Fleet workflow API platform.",
                        "source_type": "website",
                        "metadata": {"page_category": "product"},
                    }
                ],
            }
        ],
    }


class K2SyncTest(unittest.TestCase):
    def test_backend_sync_manifest_dry_run_and_apply(self) -> None:
        backend = K2Backend(api_key="test-key", base_url="http://k2.local")

        dry_run = backend.sync_manifest(sample_run())
        self.assertEqual(dry_run["status"], "dry_run")
        self.assertEqual(dry_run["document_count"], 3)

        manifest = backend.build_manifest(sample_run())
        self.assertIn("linkedin_urls", manifest["metadata_keys"])
        self.assertIn("marketplace_urls", manifest["metadata_keys"])
        self.assertIn("Public profiles and resources", manifest["documents"][0]["text"])

        client = FakeK2Client()
        applied = backend.sync_manifest(sample_run(), apply=True, client=client)
        self.assertEqual(applied["status"], "uploaded")
        self.assertEqual(applied["document_count"], 3)
        self.assertEqual(len(client.uploaded[0][1]), 3)

    def test_backend_answer_question_uses_k2_corpus_metadata_filter(self) -> None:
        run = sample_run()
        run["k2"] = {"status": "uploaded", "corpus_id": "corpus-1"}
        backend = K2Backend(api_key="test-key", base_url="http://k2.local")

        answer = backend.answer_question(run, "Which account has API evidence?", client=FakeK2Client())

        self.assertEqual(answer["status"], "ok")
        self.assertEqual(answer["provider"], "k2")
        self.assertEqual(answer["corpus_id"], "corpus-1")
        self.assertEqual(answer["citations"][0]["company"], "Mojio")
        self.assertEqual(answer["citations"][0]["source_type"], "website")

    def test_cli_dry_run_from_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.save_run(sample_run())

            with redirect_stdout(StringIO()):
                exit_code = main(["--run-id", "run-test", "--state-dir", tmp])

            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
