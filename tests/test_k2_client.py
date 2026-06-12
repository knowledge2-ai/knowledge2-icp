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
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0).decode("utf-8"))
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

            self.assertEqual(project["id"], "p1")
            self.assertEqual(corpus["id"], "c1")
            self.assertEqual(upload["count"], 1)
            self.assertEqual(answer["answer"], "K2 answer")
            self.assertTrue(all(call["api_key"] == "test-key" for call in calls))
            upload_call = calls[-2]
            self.assertEqual(upload_call["body"]["documents"][0]["source_uri"], "inline://one")
            generate_call = calls[-1]
            self.assertEqual(generate_call["body"]["top_k"], 8)
            self.assertEqual(generate_call["body"]["hybrid"]["fusion_mode"], "rrf")
            self.assertEqual(generate_call["body"]["filters"]["condition"], "and")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
