from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from icp_engine.app_store import AppStore
from icp_engine.discovery import research_discovery
from icp_engine.parallel_search import MCP_URL, ParallelSearchError, search_web
from icp_engine.research import ResearchPipeline
from icp_engine.tenant import Branding
from icp_engine.web import GTMApp, make_handler


HAS_MCP = importlib.util.find_spec('mcp') is not None
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


class MCPFixture:
    """Exercise the official MCP client with observed HTTP requests/responses."""

    def __init__(self, *, sse=False, text=False, tool_result=None, failure=None):
        self.calls = []
        self.sse, self.text, self.tool_result, self.failure = sse, text, tool_result, failure

    async def handle(self, request):
        import httpx
        assert str(request.url) == MCP_URL
        assert request.headers['user-agent'] == Branding().discovery_user_agent
        assert not any(name in request.headers for name in ['authorization', 'x-api-key'])
        payload = json.loads(request.content) if request.content else {}
        self.calls.append({'request': request, 'payload': payload})
        if request.method == 'GET':
            return httpx.Response(405)
        if request.method == 'DELETE':
            return httpx.Response(200)
        method = payload['method']
        assert 'application/json' in request.headers['accept']
        assert 'text/event-stream' in request.headers['accept']
        if method == 'initialize':
            self.protocol = payload['params']['protocolVersion']
            result = {'protocolVersion': self.protocol, 'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'Parallel fixture', 'version': '1.0'}}
        else:
            assert request.headers['mcp-session-id'] == 'fixture-mcp-session'
            assert request.headers['mcp-protocol-version'] == self.protocol
            if method == 'notifications/initialized':
                assert 'id' not in payload
                return httpx.Response(202)
            if method == 'tools/list':
                result = {'tools': [{'name': 'web_search', 'inputSchema': {'type': 'object'}}]}
            else:
                assert method == 'tools/call'
                assert payload['params']['name'] == 'web_search'
                args = payload['params']['arguments']
                assert args['search_queries'] == ['fleet software']
                assert 'fleet software' in args['objective']
                assert len(args['session_id']) >= 32
                if self.failure == 'http':
                    return httpx.Response(429)
                if self.failure in {'trickle', 'truncated'}:
                    failure = self.failure
                    class Stream(httpx.AsyncByteStream):
                        async def __aiter__(self):
                            if failure == 'truncated':
                                yield b'data: {"jsonrpc":'
                                raise httpx.RemoteProtocolError('incomplete chunked response')
                            while True:
                                yield b': keepalive\n\n'
                                await asyncio.sleep(.01)
                    return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Stream())
                data = {'results': RESULTS}
                result = self.tool_result if self.tool_result is not None else (
                    {'content': [{'type': 'text', 'text': json.dumps(data)}]} if self.text else {'content': [], 'structuredContent': data}
                )
        message = {'jsonrpc': '2.0', 'id': payload['id'], 'result': result}
        headers = {'mcp-session-id': 'fixture-mcp-session'}
        if self.sse:
            headers['content-type'] = 'text/event-stream'
            return httpx.Response(200, headers=headers, content=b': keepalive\n\ndata: ' + json.dumps(message).encode() + b'\n\n')
        return httpx.Response(200, headers=headers, json=message)

    def installed(self):
        import httpx
        real_client = httpx.AsyncClient
        def client(**kwargs):
            return real_client(transport=httpx.MockTransport(self.handle), **kwargs)
        return patch('httpx.AsyncClient', side_effect=client)


class OptionalInstallTest(unittest.TestCase):
    def test_missing_extra_reports_setup_without_fallback(self):
        import builtins
        original = builtins.__import__
        def missing(name, *args, **kwargs):
            if name == 'mcp':
                raise ImportError('extra absent')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=missing), \
                patch('icp_engine.discovery._duckduckgo_discovery', side_effect=AssertionError('unexpected fallback')):
            candidates, warnings, provider = research_discovery('fleet software', provider='parallel')
        self.assertEqual((candidates, provider), ([], 'none'))
        self.assertIn('.[parallel]', warnings[0])


@unittest.skipUnless(HAS_MCP, 'Install .[parallel] to exercise the optional MCP client.')
class ParallelDiscoveryTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_saved_provider_runs_through_qualification_and_persistence(self):
        fixture = MCPFixture()
        with tempfile.TemporaryDirectory() as tmp, fixture.installed():
            store = AppStore(Path(tmp))
            store.save_settings({'discovery_provider': 'parallel'})
            run = ResearchPipeline(AppStore(Path(tmp))).create_run(query='fleet software', fetch=False, include_github=False)
            self.assertEqual(run['discovery']['provider'], 'parallel')
            self.assertEqual(run['status'], 'completed')
            self.assertEqual([lead['score']['company']['domain'] for lead in run['leads']], ['moj.io', 'automate.co.za'])
            self.assertEqual(run['leads'][0]['candidate']['source_url'], RESULTS[0]['url'])
            self.assertIn('linkedin.com', run['leads'][0]['candidate']['linkedin_urls'][0])
            self.assertEqual(store.load_run(run['id'])['discovery']['provider'], 'parallel')
            methods = [call['payload'].get('method') for call in fixture.calls]
            for method in ['initialize', 'notifications/initialized', 'tools/list', 'tools/call']:
                self.assertIn(method, methods)
            self.assertEqual(fixture.calls[-1]['request'].method, 'DELETE')

    def test_json_sse_and_text_content(self):
        for sse, text in [(False, False), (True, False), (False, True), (True, True)]:
            fixture = MCPFixture(sse=sse, text=text)
            with self.subTest(sse=sse, text=text), fixture.installed():
                candidates, warnings, provider = research_discovery('fleet software', provider='parallel', max_results=1)
                self.assertEqual((provider, len(candidates), warnings), ('parallel', 1, []))
                self.assertEqual(candidates[0].source_url, RESULTS[0]['url'])

    def test_parallel_precedes_other_credentials_and_reuses_conversation_id(self):
        fixture = MCPFixture()
        with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'unused', 'SERPER_API_KEY': 'unused'}), fixture.installed():
            for _ in range(2):
                self.assertEqual(research_discovery('fleet software', provider='parallel')[2], 'parallel')
        ids = [call['payload']['params']['arguments']['session_id'] for call in fixture.calls if call['payload'].get('method') == 'tools/call']
        self.assertEqual(ids[0], ids[1])

    def test_unconfigured_and_explicit_choices_do_not_call_parallel(self):
        with patch('icp_engine.parallel_search.search_web', side_effect=AssertionError('Parallel is opt-in')):
            for provider in ['auto', 'duckduckgo', 'serper']:
                self.assertEqual(research_discovery('fleet software', provider=provider, search_fetcher=lambda _: DDG_HTML)[2], 'duckduckgo')
            self.assertEqual(research_discovery(' ', provider='parallel')[2], 'none')

    def test_disabled_search_retains_manual_seeds_without_requests(self):
        with tempfile.TemporaryDirectory() as tmp, patch('icp_engine.parallel_search.search_web', side_effect=AssertionError('disabled')):
            store = AppStore(Path(tmp))
            store.save_settings({'discovery_provider': 'parallel', 'use_serp_discovery': False})
            candidates, warnings, provider = ResearchPipeline(store).discover('fleet software', seed_text='Mojio, moj.io')
            self.assertEqual(([item.domain for item in candidates], provider), (['moj.io'], 'none'))
            self.assertIn('disabled', warnings[0])

    def test_transport_tool_and_malformed_errors_never_fall_back(self):
        fixtures = [MCPFixture(failure='http'), MCPFixture(failure='truncated'),
                    MCPFixture(tool_result={'isError': True, 'content': [{'type': 'text', 'text': 'Free anonymous quota exhausted'}]}),
                    MCPFixture(tool_result={'content': [], 'structuredContent': {'results': 'bad'}}),
                    MCPFixture(tool_result={'content': [{'type': 'text', 'text': 'not json'}]})]
        for fixture in fixtures:
            with self.subTest(failure=fixture.failure), fixture.installed(), \
                    patch('icp_engine.discovery._duckduckgo_discovery', side_effect=AssertionError('unexpected fallback')):
                candidates, warnings, provider = research_discovery('fleet software', provider='parallel')
                self.assertEqual((candidates, provider), ([], 'none'))
                self.assertTrue(warnings)

    def test_trickling_stream_obeys_overall_deadline(self):
        fixture = MCPFixture(failure='trickle')
        started = time.monotonic()
        with fixture.installed(), patch('icp_engine.discovery.SEARCH_TIMEOUT_SECONDS', .1):
            candidates, warnings, provider = research_discovery('fleet software', provider='parallel')
        self.assertEqual((candidates, provider), ([], 'none'))
        self.assertIn('timed out', warnings[0])
        self.assertLess(time.monotonic() - started, .75)
        # Exiting the deadline also closes the SDK's HTTP client and task groups.
        self.assertTrue(any(call['payload'].get('method') == 'tools/call' for call in fixture.calls))

    def test_interrupt_propagates(self):
        # Close the unawaited coroutine because this fixture interrupts before
        # asyncio takes ownership of it.
        def interrupt(coro):
            coro.close()
            raise KeyboardInterrupt
        with patch('asyncio.run', side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            research_discovery('fleet software', provider='parallel')

    def test_api_authorization_and_search_budget_precede_mcp(self):
        fixture = MCPFixture()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'ICP_ADMIN_TOKEN': 'test-token'}), fixture.installed():
            store = AppStore(Path(tmp))
            store.save_settings({'discovery_provider': 'parallel', 'provider_limits': {'daily': {'search': 1}}})
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(GTMApp(store=store)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}/api/search'
            # Earlier tests may have initialized urllib's global proxy opener.
            # Keep this loopback client independent of that cached process state.
            local_client = build_opener(ProxyHandler({}))
            try:
                def post(token):
                    headers = {'Content-Type': 'application/json'}
                    if token:
                        headers['Authorization'] = 'Bearer test-token'
                    with local_client.open(Request(url, data=b'{"query":"fleet software"}', headers=headers)) as response:
                        return json.load(response)
                with self.assertRaises(HTTPError) as denied:
                    post(False)
                self.assertEqual(denied.exception.code, 401)
                self.assertEqual(fixture.calls, [])
                self.assertEqual(post(True)['candidates'][0]['domain'], 'moj.io')
                count = len(fixture.calls)
                with self.assertRaises(HTTPError) as limited:
                    post(True)
                self.assertEqual(limited.exception.code, 429)
                self.assertEqual(len(fixture.calls), count)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
