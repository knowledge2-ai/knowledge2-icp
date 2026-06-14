from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from icp_engine.app_store import AppStore
from icp_engine.web import GTMApp, make_handler


def _start_server(app: GTMApp) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


class CriteriaSuggestTest(unittest.TestCase):
    def test_suggest_returns_proposal_and_persists_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            app = GTMApp(store=store)
            before = store.load_criteria()
            server, thread, base_url = _start_server(app)
            proposal = {
                "markdown": "# Improved ICP\n\n- Sharper disqualifiers.",
                "rationale": "Tightens the AI-posture rubric.",
                "diff_summary": "Clarified ai_posture levels.",
                "model": "claude:test",
            }
            try:
                with patch("icp_engine.web.suggest_criteria", return_value=proposal) as suggester:
                    result = _json_post(f"{base_url}/api/criteria/suggest", {"markdown": before["markdown"]})

                self.assertEqual(result["proposal"]["markdown"], proposal["markdown"])
                self.assertEqual(result["current_hash"], before["hash"])
                suggester.assert_called_once()

                # Nothing is persisted until the user saves through the versioning flow.
                self.assertEqual(store.load_criteria()["hash"], before["hash"])
                self.assertEqual(store.load_criteria()["markdown"], before["markdown"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_suggest_requires_auth_when_admin_token_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            app = GTMApp(store=store, admin_token="test-token")
            server, thread, base_url = _start_server(app)
            proposal = {"markdown": "# x", "rationale": "", "diff_summary": "", "model": "claude:test"}
            try:
                with patch("icp_engine.web.suggest_criteria", return_value=proposal) as suggester:
                    with self.assertRaises(HTTPError) as missing:
                        _json_post(f"{base_url}/api/criteria/suggest", {"markdown": "# x"})
                    self.assertEqual(missing.exception.code, 401)
                    suggester.assert_not_called()

                    ok = _json_post(
                        f"{base_url}/api/criteria/suggest",
                        {"markdown": "# x"},
                        headers={"Authorization": "Bearer test-token"},
                    )
                    self.assertEqual(ok["proposal"]["model"], "claude:test")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


def _json_post(url: str, payload: dict[str, object], headers: dict[str, str] | None = None) -> dict[str, object]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers=request_headers)
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
