from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from icp_engine.k2_client import K2RestClient


class K2ClientTest(unittest.TestCase):
    def test_project_corpus_and_upload_requests(self) -> None:
        calls: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                calls.append({"method": "GET", "path": self.path, "api_key": self.headers.get("X-API-Key")})
                if self.path.startswith("/v1/projects"):
                    self._json({"projects": [{"id": "p1", "name": "Project"}]})
                    return
                if self.path.startswith("/v1/corpora"):
                    self._json({"corpora": []})
                    return
                self.send_response(404)
                self.end_headers()

            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0)
                body = json.loads(raw.decode("utf-8")) if raw else {}
                calls.append({"method": "POST", "path": self.path, "body": body, "api_key": self.headers.get("X-API-Key")})
                if self.path == "/v1/corpora":
                    self._json({"id": "c1", "name": body["name"], "project_id": body["project_id"]})
                    return
                if self.path == "/v1/corpora/c1/documents:batch":
                    self._json({"job_id": "j1", "batch_id": "b1", "count": len(body["documents"])})
                    return
                if self.path == "/v1/corpora/c1/search:generate":
                    self._json({"answer": "K2 answer", "model": "test-model", "body": body, "results": []})
                    return
                if self.path == "/v1/pipeline-specs/pipe-1/dry-run":
                    self._json({"valid": True, "issues": [], "simulated_nodes": []})
                    return
                if self.path == "/v1/pipeline-specs/pipe-1/apply":
                    self._json({"created_agent_ids": [], "updated_agent_ids": [], "activate_entities": body.get("activate_entities")})
                    return
                if self.path == "/v1/pipeline-specs/pipe-1/trigger":
                    self._json({"pipeline_run_id": "pipeline-run-1", "child_run_ids": ["job-1"]})
                    return
                if self.path == "/v1/pipeline-specs/pipe-1/backfill":
                    self._json({"pipeline_run_id": "pipeline-run-2", "start_from": body.get("start_from"), "layers": []})
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return

            def _json(self, payload: dict[str, object]) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = K2RestClient(api_key="test-key", base_url=f"http://127.0.0.1:{server.server_port}")
            project = client.ensure_project("Project")
            corpus = client.ensure_corpus(project["id"], "Corpus", "Description")
            upload = client.upload_documents(corpus["id"], [{"sourceUri": "inline://one", "rawText": "Hello", "metadata": {}}])
            answer = client.generate_answer(corpus["id"], "Which company?", filters={"condition": "and", "filters": []})
            dry_run = client.dry_run_pipeline_spec("pipe-1")
            applied = client.apply_pipeline_spec("pipe-1", activate_entities=False)
            triggered = client.trigger_pipeline_spec("pipe-1")
            backfilled = client.backfill_pipeline_spec("pipe-1", start_from="2026-05-01T00:00:00Z")

            self.assertEqual(project["id"], "p1")
            self.assertEqual(corpus["id"], "c1")
            self.assertEqual(upload["count"], 1)
            self.assertEqual(answer["answer"], "K2 answer")
            self.assertTrue(dry_run["valid"])
            self.assertFalse(applied["activate_entities"])
            self.assertEqual(triggered["pipeline_run_id"], "pipeline-run-1")
            self.assertEqual(backfilled["start_from"], "2026-05-01T00:00:00Z")
            self.assertTrue(all(call["api_key"] == "test-key" for call in calls))
            upload_call = next(call for call in calls if call["path"] == "/v1/corpora/c1/documents:batch")
            self.assertEqual(upload_call["body"]["documents"][0]["source_uri"], "inline://one")
            generate_call = next(call for call in calls if call["path"] == "/v1/corpora/c1/search:generate")
            self.assertEqual(generate_call["body"]["top_k"], 8)
            self.assertEqual(generate_call["body"]["hybrid"]["fusion_mode"], "rrf")
            self.assertEqual(generate_call["body"]["filters"]["condition"], "and")
            apply_call = next(call for call in calls if call["path"] == "/v1/pipeline-specs/pipe-1/apply")
            self.assertEqual(apply_call["body"]["activate_entities"], False)
            backfill_call = next(call for call in calls if call["path"] == "/v1/pipeline-specs/pipe-1/backfill")
            self.assertEqual(backfill_call["body"]["start_from"], "2026-05-01T00:00:00Z")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_search_batch_includes_filters_only_when_present(self) -> None:
        calls: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0)
                body = json.loads(raw.decode("utf-8")) if raw else {}
                calls.append({"path": self.path, "body": body})
                raw_out = json.dumps({"responses": [{"results": []}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw_out)))
                self.end_headers()
                self.wfile.write(raw_out)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = K2RestClient(api_key="test-key", base_url=f"http://127.0.0.1:{server.server_port}")
            client.search_batch("c1", ["moj.io"], top_k=3)
            client.search_batch(
                "c1",
                ["moj.io"],
                top_k=3,
                filters={"condition": "and", "filters": [{"key": "tier", "op": "==", "value": "A"}]},
            )

            self.assertNotIn("filters", calls[0]["body"])
            self.assertEqual(calls[1]["body"]["filters"]["filters"][0]["key"], "tier")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
