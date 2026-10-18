from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from icp_engine.app_store import AppStore
from icp_engine.discovery import research_discovery
from icp_engine.parallel_search import MCP_URL, PROTOCOL_VERSION, ParallelSearchError, search_web
from icp_engine.research import ResearchPipeline
from icp_engine.tenant import Branding
from icp_engine.web import GTMApp, make_handler


RESULTS = [
    {"url": "https://www.moj.io/platform", "title": "Mojio - Connected Mobility", "excerpts": ["Fleet software."]},
    {"url": "https://www.moj.io/", "title": "Mojio"},
    {"url": "https://www.linkedin.com/company/mojio", "title": "Mojio LinkedIn"},
    {"url": "https://automate.co.za/", "title": "Automate | Dealer Management Software"},
    {"url": "file:///tmp/company", "title": "Invalid scheme"},
    {"url": "https://secret@example.com/", "title": "Credentials"},
    {"url": "https://[", "title": "Invalid URL"},
    {"url": None},
]
DDG_HTML = '<a class="result__a" href="https://moj.io/">Mojio</a>'


class Response(io.BytesIO):
    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        super().__init__(body)
        self.headers = headers


class MCPFixture:
    """Observe real request construction at the HTTP boundary, not a helper stub."""

    def __init__(self, *, sse: bool = False, text: bool = False, tool_result: object = None) -> None:
        self.calls: list[dict] = []
        self.sse = sse
        self.text = text
        self.tool_result = tool_result

    def __call__(self, request: Request, *, timeout: float) -> Response:
        payload = json.loads(request.data)
        headers = dict(request.header_items())
        assert request.full_url == MCP_URL
        assert headers["User-agent"] == Branding().discovery_user_agent
        assert headers["Accept"] == "application/json, text/event-stream"
        assert not any(name.lower() in {"authorization", "x-api-key"} for name in headers)
        assert 0 < timeout <= 10
        self.calls.append({"payload": payload, "headers": headers, "timeout": timeout, "url": request.full_url})
        method = payload["method"]
        if method == "initialize":
            assert payload["params"]["protocolVersion"] == PROTOCOL_VERSION
            result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}}
        else:
            assert headers["Mcp-session-id"] == "fixture-mcp-session"
            assert headers["Mcp-protocol-version"] == PROTOCOL_VERSION
            if method == "notifications/initialized":
                assert "id" not in payload
                return Response(b"", {})
            if method == "tools/list":
                result = {"tools": [{"name": "web_search"}]}
            else:
                assert method == "tools/call"
                assert payload["params"]["name"] == "web_search"
                args = payload["params"]["arguments"]
                assert args["search_queries"] == ["fleet software"]
                assert "fleet software" in args["objective"]
                assert len(args["session_id"]) >= 32
                data = {"results": RESULTS}
                result = self.tool_result if self.tool_result is not None else (
                    {"content": [{"type": "text", "text": json.dumps(data)}]} if self.text else {"structuredContent": data}
                )
        message = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        raw = json.dumps(message).encode()
        content_type = "application/json"
        if self.sse:
            content_type = "text/event-stream"
            raw = b': keepalive\n\ndata: {"jsonrpc":"2.0","method":"notifications/message"}\n\n' + b"event: message\ndata: " + raw + b"\n\n"
        return Response(raw, {"Content-Type": content_type, "Mcp-Session-Id": "fixture-mcp-session"})


class ParallelDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_saved_provider_runs_through_qualification_and_persistence(self) -> None:
        fixture = MCPFixture()
        with tempfile.TemporaryDirectory() as tmp, patch("icp_engine.parallel_search.urlopen", fixture):
            store = AppStore(Path(tmp))
            store.save_settings({"discovery_provider": "parallel"})
            # Reopen the store to prove the normal saved-setting resolver is used.
            pipeline = ResearchPipeline(AppStore(Path(tmp)))
            run = pipeline.create_run(query="fleet software", fetch=False, include_github=False)
            self.assertEqual(run["discovery"]["provider"], "parallel")
            self.assertEqual(run["status"], "completed")
            self.assertEqual([lead["score"]["company"]["domain"] for lead in run["leads"]], ["moj.io", "automate.co.za"])
            self.assertEqual(run["leads"][0]["candidate"]["source_url"], RESULTS[0]["url"])
            self.assertIn("linkedin.com", run["leads"][0]["candidate"]["linkedin_urls"][0])
            self.assertEqual(store.load_run(run["id"])["discovery"]["provider"], "parallel")
            self.assertEqual([call["payload"]["method"] for call in fixture.calls],
                             ["initialize", "notifications/initialized", "tools/list", "tools/call"])

    def test_json_sse_and_text_content(self) -> None:
        for sse, text in [(False, False), (True, False), (False, True), (True, True)]:
            with self.subTest(sse=sse, text=text), patch("icp_engine.parallel_search.urlopen", MCPFixture(sse=sse, text=text)):
                candidates, warnings, provider = research_discovery("fleet software", provider="parallel", max_results=1)
                self.assertEqual(provider, "parallel")
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0].source_url, RESULTS[0]["url"])
                self.assertEqual(warnings, [])

    def test_parallel_precedes_other_credentials_and_reuses_conversation_id(self) -> None:
        fixture = MCPFixture()
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "unused", "SERPER_API_KEY": "unused"}), \
                patch("icp_engine.parallel_search.urlopen", fixture), \
                patch("icp_engine.discovery._duckduckgo_discovery", side_effect=AssertionError("unexpected fallback")):
            for _ in range(2):
                self.assertEqual(research_discovery("fleet software", provider="parallel")[2], "parallel")
        ids = [call["payload"]["params"]["arguments"]["session_id"] for call in fixture.calls if call["payload"]["method"] == "tools/call"]
        self.assertEqual(ids[0], ids[1])

    def test_unconfigured_and_explicit_choices_do_not_call_parallel(self) -> None:
        with patch("icp_engine.parallel_search.urlopen", side_effect=AssertionError("Parallel is opt-in")):
            for provider in ["auto", "duckduckgo", "serper"]:
                self.assertEqual(research_discovery("fleet software", provider=provider, search_fetcher=lambda _: DDG_HTML)[2], "duckduckgo")
            self.assertEqual(research_discovery(" ", provider="parallel")[2], "none")

    def test_disabled_search_retains_manual_seeds_without_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("icp_engine.parallel_search.urlopen", side_effect=AssertionError("disabled")):
            store = AppStore(Path(tmp))
            store.save_settings({"discovery_provider": "parallel", "use_serp_discovery": False})
            candidates, warnings, provider = ResearchPipeline(store).discover("fleet software", seed_text="Mojio, moj.io")
            self.assertEqual([item.domain for item in candidates], ["moj.io"])
            self.assertEqual(provider, "none")
            self.assertIn("disabled", warnings[0])

    def test_errors_and_timeouts_never_fall_back(self) -> None:
        for error in [TimeoutError(), URLError("offline"), HTTPError(MCP_URL, 429, "quota", {}, None)]:
            with self.subTest(error=type(error).__name__), patch("icp_engine.parallel_search.urlopen", side_effect=error), \
                    patch("icp_engine.discovery._duckduckgo_discovery", side_effect=AssertionError("unexpected fallback")):
                candidates, warnings, provider = research_discovery("fleet software", provider="parallel")
                self.assertEqual((candidates, provider), ([], "none"))
                self.assertTrue(warnings)

    def test_tool_errors_and_malformed_payloads_are_warnings(self) -> None:
        for result in [
            {"isError": True, "content": [{"type": "text", "text": "Free anonymous quota exhausted"}]},
            {"structuredContent": {"results": "bad"}}, {"content": None},
            {"content": [{"type": "text", "text": "not json"}]},
        ]:
            with self.subTest(result=result), patch("icp_engine.parallel_search.urlopen", MCPFixture(tool_result=result)):
                candidates, warnings, provider = research_discovery("fleet software", provider="parallel")
                self.assertEqual((candidates, provider), ([], "none"))
                self.assertTrue(warnings)

    def test_malformed_rpc_missing_tool_and_oversized_response(self) -> None:
        responses = [b"not json", b'{"jsonrpc":"2.0","id":999,"result":{}}',
                     b'{"jsonrpc":"2.0","id":1,"error":{"code":-1}}', b"x" * 101]
        for raw in responses:
            with self.subTest(raw=raw[:50]), patch("icp_engine.parallel_search.MAX_RESPONSE_BYTES", 100), \
                    patch("icp_engine.parallel_search.urlopen", return_value=Response(raw, {})):
                with self.assertRaises(ParallelSearchError):
                    search_web("fleet software")

    def test_timeout_budget_and_cancellation(self) -> None:
        fixture = MCPFixture()
        with patch("icp_engine.parallel_search.time.monotonic", side_effect=[0, 1, 11]), \
                patch("icp_engine.parallel_search.urlopen", fixture):
            with self.assertRaisesRegex(ParallelSearchError, "timed out"):
                search_web("fleet software")
        self.assertEqual(len(fixture.calls), 1)
        with patch("icp_engine.parallel_search.urlopen", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                research_discovery("fleet software", provider="parallel")

    def test_api_authorization_and_search_budget_precede_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ICP_ADMIN_TOKEN": "test-token"}), \
                patch("icp_engine.parallel_search.urlopen") as network:
            store = AppStore(Path(tmp))
            store.save_settings({"discovery_provider": "parallel", "provider_limits": {"daily": {"search": 1}}})
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(GTMApp(store=store)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/api/search"
            try:
                def post(token: bool) -> dict:
                    headers = {"Content-Type": "application/json"}
                    if token:
                        headers["Authorization"] = "Bearer test-token"
                    with urlopen(Request(url, data=b'{"query":"fleet software"}', headers=headers)) as response:
                        return json.load(response)

                with self.assertRaises(HTTPError) as denied:
                    post(False)
                self.assertEqual(denied.exception.code, 401)
                network.assert_not_called()
                fixture = MCPFixture()
                network.side_effect = fixture
                self.assertEqual(post(True)["candidates"][0]["domain"], "moj.io")
                self.assertEqual(network.call_count, 4)
                with self.assertRaises(HTTPError) as limited:
                    post(True)
                self.assertEqual(limited.exception.code, 429)
                self.assertEqual(network.call_count, 4)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
