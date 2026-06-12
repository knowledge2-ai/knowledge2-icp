from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from pathlib import Path
from urllib.request import Request, urlopen

from icp_engine.app_store import AppStore
from icp_engine.models import CompanyInput, Evidence
from icp_engine.research import ResearchPipeline
from icp_engine.web import GTMApp, _is_loopback_bind_host, run_server, make_handler


def fake_evidence(company: CompanyInput, cache_dir: Path) -> tuple[list[Evidence], list[str]]:
    return (
        [
            Evidence(
                evidence_id="e1",
                url=f"https://{company.domain}/about",
                title="About",
                text="Founded in 2010. B2B software platform with workflow, records, API, integrations, and enterprise customers.",
                metadata={
                    "page_category": "company",
                    "links": [f"https://{company.domain}/pricing", "https://www.linkedin.com/company/acme"],
                },
            )
        ],
        [],
    )


class WebApiTest(unittest.TestCase):
    def test_state_criteria_and_run_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            app = GTMApp(store=store, pipeline=pipeline)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = _json_get(f"{base_url}/api/state")
                self.assertIn("criteria", state)

                health = _json_get(f"{base_url}/healthz")
                self.assertEqual(health["status"], "ok")
                self.assertFalse(health["auth_required"])

                readiness = _json_get(f"{base_url}/api/health")
                self.assertEqual(readiness["status"], "ok")
                self.assertIn("provider_status", readiness)

                updated = _json_post(f"{base_url}/api/criteria", {"markdown": "# ICP\n\n- Test"})
                self.assertEqual(updated["criteria"]["markdown"], "# ICP\n\n- Test\n")

                run = _json_post(
                    f"{base_url}/api/runs",
                    {
                        "query": "",
                        "seed_text": "Acme Fleet, acme.example",
                        "include_github": False,
                        "fetch": True,
                    },
                )
                self.assertEqual(run["status"], "completed")
                self.assertEqual(len(run["leads"]), 1)

                prospects = _json_get(f"{base_url}/api/runs/{run['id']}/prospects")
                self.assertGreaterEqual(prospects["prospect_count"], 1)
                self.assertIn("prospects", prospects)

                prospects_csv = _text_get(f"{base_url}/api/runs/{run['id']}/prospects.csv")
                self.assertIn("company,domain", prospects_csv)
                self.assertIn("Acme Fleet", prospects_csv)

                manifest = _json_get(f"{base_url}/api/runs/{run['id']}/k2-manifest")
                self.assertGreaterEqual(manifest["document_count"], 2)
                self.assertIn("source_type", manifest["metadata_keys"])

                exported = _json_post(f"{base_url}/api/runs/{run['id']}/k2-export", {})
                self.assertTrue(Path(exported["export_path"]).exists())

                sync = _json_post(f"{base_url}/api/runs/{run['id']}/k2-sync", {"apply": False})
                self.assertEqual(sync["status"], "dry_run")
                self.assertGreaterEqual(sync["document_count"], 2)

                preview = _json_post(
                    f"{base_url}/api/search",
                    {
                        "query": "",
                        "seed_text": "Selected Fleet, selected.example",
                        "max_companies": 3,
                    },
                )
                self.assertEqual(preview["candidates"][0]["domain"], "selected.example")

                selected_run = _json_post(
                    f"{base_url}/api/runs",
                    {
                        "query": "selected preview",
                        "candidates": [
                            {
                                "company": "Selected Fleet",
                                "domain": "selected.example",
                                "source_url": "https://selected.example",
                                "source_title": "Selected preview candidate",
                                "github_urls": ["https://github.com/selected"],
                                "linkedin_urls": ["https://www.linkedin.com/company/selected"],
                            }
                        ],
                        "include_github": False,
                        "fetch": True,
                    },
                )
                self.assertEqual(len(selected_run["leads"]), 1)
                selected_lead = selected_run["leads"][0]
                self.assertEqual(selected_lead["candidate"]["source_title"], "Selected preview candidate")
                self.assertIn("https://github.com/selected", selected_lead["metadata"]["source_refs"]["github_urls"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_api_auth_when_admin_token_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            app = GTMApp(store=store, pipeline=pipeline, admin_token="test-token")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                self.assertIn("<!doctype html>", _text_get(f"{base_url}/"))

                public_health = _json_get(f"{base_url}/healthz")
                self.assertEqual(public_health["status"], "ok")
                self.assertTrue(public_health["auth_required"])

                with self.assertRaises(HTTPError) as missing:
                    _json_get(f"{base_url}/api/state")
                self.assertEqual(missing.exception.code, 401)
                self.assertEqual(missing.exception.headers["WWW-Authenticate"], 'Bearer realm="knowledge2-icp"')

                with self.assertRaises(HTTPError) as bad_token:
                    _json_get(f"{base_url}/api/state", headers={"Authorization": "Bearer wrong"})
                self.assertEqual(bad_token.exception.code, 401)

                state = _json_get(f"{base_url}/api/state", headers={"Authorization": "Bearer test-token"})
                self.assertIn("criteria", state)

                readiness = _json_get(f"{base_url}/api/health", headers={"Authorization": "Bearer test-token"})
                self.assertEqual(readiness["status"], "ok")
                self.assertTrue(readiness["auth_required"])
                self.assertIn("provider_status", readiness)

                updated = _json_post(
                    f"{base_url}/api/criteria",
                    {"markdown": "# Protected ICP"},
                    headers={"Authorization": "Bearer test-token"},
                )
                self.assertEqual(updated["criteria"]["markdown"], "# Protected ICP\n")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_public_bind_requires_admin_token(self) -> None:
        with self.assertRaises(ValueError):
            run_server("0.0.0.0", 0, admin_token="", allow_open_api=False)

    def test_loopback_bind_host_detection(self) -> None:
        self.assertTrue(_is_loopback_bind_host("127.0.0.1"))
        self.assertTrue(_is_loopback_bind_host("::1"))
        self.assertTrue(_is_loopback_bind_host("localhost"))
        self.assertFalse(_is_loopback_bind_host("0.0.0.0"))


def _json_get(url: str, headers: dict[str, str] | None = None) -> dict[str, object]:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _text_get(url: str, headers: dict[str, str] | None = None) -> str:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=5) as response:
        return response.read().decode("utf-8")


def _json_post(url: str, payload: dict[str, object], headers: dict[str, str] | None = None) -> dict[str, object]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=request_headers,
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
