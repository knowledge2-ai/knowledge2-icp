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
                self.assertEqual(state["eval_summary"]["latest_status"], "not_run")
                original_hash = state["criteria"]["hash"]

                health = _json_get(f"{base_url}/healthz")
                self.assertEqual(health["status"], "ok")
                self.assertFalse(health["auth_required"])

                readiness = _json_get(f"{base_url}/api/health")
                self.assertEqual(readiness["status"], "ok")
                self.assertIn("provider_status", readiness)
                self.assertIn("provider_controls", readiness)

                workspace = _json_get(f"{base_url}/api/k2-workspace")
                self.assertIn(workspace["source"], {"blueprint", "summary"})
                self.assertIn("corpora", workspace)
                self.assertGreaterEqual(len(workspace["corpora"]), 5)
                self.assertFalse(workspace["configured"])

                settings = _json_post(
                    f"{base_url}/api/settings",
                    {
                        "default_query": "fleet workflow data limited AI positioning",
                        "max_companies": 42,
                        "max_pages": 7,
                        "fetch_website_evidence": False,
                        "provider_limits": {
                            "daily": {"search": 17},
                            "rate_per_minute": {"research": 9},
                            "per_run": {"max_companies": 42},
                        },
                    },
                )
                self.assertEqual(settings["settings"]["default_query"], "fleet workflow data limited AI positioning")
                self.assertEqual(settings["settings"]["max_companies"], 42)
                self.assertFalse(settings["settings"]["fetch_website_evidence"])
                self.assertEqual(settings["settings"]["provider_limits"]["daily"]["search"], 17)
                self.assertEqual(_json_get(f"{base_url}/api/settings")["settings"]["max_pages"], 7)

                updated = _json_post(f"{base_url}/api/criteria", {"markdown": "# ICP  \n\n* Test"})
                self.assertEqual(updated["criteria"]["markdown"], "# ICP\n\n- Test\n")
                self.assertIn("versions", updated)
                self.assertIn("lint", updated)
                self.assertGreaterEqual(len(updated["versions"]), 2)

                lint = _json_post(f"{base_url}/api/criteria/lint", {"markdown": "# ICP  \n* Test"})
                self.assertTrue(lint["changed"])
                self.assertGreaterEqual(lint["warning_count"], 1)

                versions = _json_get(f"{base_url}/api/criteria/versions")
                self.assertIn(original_hash, {item["hash"] for item in versions["versions"]})

                restored = _json_post(f"{base_url}/api/criteria/restore", {"id": original_hash})
                self.assertEqual(restored["criteria"]["hash"], original_hash)

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

                impact = _json_post(
                    f"{base_url}/api/criteria/impact",
                    {
                        "run_id": run["id"],
                        "markdown": "# Impact ICP\n\n- Tier A threshold: 90\n- Tier B threshold: 70\n- 50-2000 employees\n",
                    },
                )
                self.assertEqual(impact["run_id"], run["id"])
                self.assertEqual(impact["lead_count"], 1)
                self.assertEqual(impact["proposed_profile"]["tier_a_threshold"], 90)
                self.assertIn("current_counts", impact)
                self.assertIn("proposed_counts", impact)

                lead_state = _json_post(
                    f"{base_url}/api/runs/{run['id']}/lead-state",
                    {
                        "domain": "acme.example",
                        "company": "Acme Fleet",
                        "status": "Qualified",
                        "note": "Ready for outreach.",
                        "owner": "research",
                        "tags": ["fleet", "apollo"],
                    },
                )
                self.assertEqual(lead_state["lead_state"]["status"], "Qualified")
                self.assertEqual(lead_state["status_counts"]["Qualified"], 1)

                workflow = _json_get(f"{base_url}/api/runs/{run['id']}/workflow")
                self.assertEqual(workflow["status_counts"]["Qualified"], 1)
                self.assertEqual(workflow["lead_states"][0]["domain"], "acme.example")

                bulk = _json_post(
                    f"{base_url}/api/runs/{run['id']}/lead-state/bulk",
                    {
                        "domains": ["acme.example"],
                        "status": "Exported",
                        "note": "Bulk ready for CRM.",
                    },
                )
                self.assertEqual(bulk["updated_count"], 1)
                self.assertEqual(bulk["lead_states"][0]["status"], "Exported")
                self.assertEqual(bulk["status_counts"]["Exported"], 1)

                view = _json_post(
                    f"{base_url}/api/lead-views",
                    {
                        "name": "Qualified A Accounts",
                        "filters": {"status": "Exported", "tier": "A", "source": "manual-seed"},
                        "sort": {"field": "score", "direction": "desc"},
                        "page_size": 25,
                    },
                )
                self.assertEqual(view["view"]["name"], "Qualified A Accounts")
                self.assertEqual(_json_get(f"{base_url}/api/lead-views")["views"][0]["page_size"], 25)

                source = _json_post(
                    f"{base_url}/api/sources",
                    {
                        "name": "Manual portfolio source",
                        "type": "manual_seed",
                        "value": "Mojio, moj.io\nAutomate, automate.co.za",
                        "source_group": "portfolio-expansion",
                        "schedule": "weekly",
                    },
                )
                self.assertEqual(source["source"]["type"], "manual_seed")
                source_scan = _json_post(f"{base_url}/api/sources/{source['source']['id']}/scan", {"max_companies": 5})
                self.assertEqual(source_scan["scan"]["candidate_count"], 2)
                self.assertEqual(source_scan["candidates"][0]["domain"], "moj.io")
                self.assertGreaterEqual(_json_get(f"{base_url}/api/sources")["coverage"]["unique_candidate_domains"], 2)
                self.assertIn("expansion_runs", _json_get(f"{base_url}/api/sources"))

                audit = _json_get(f"{base_url}/api/audit-log")
                self.assertIn("lead_state.updated", {item["action"] for item in audit["events"]})

                prospects = _json_get(f"{base_url}/api/runs/{run['id']}/prospects")
                self.assertGreaterEqual(prospects["prospect_count"], 1)
                self.assertIn("prospects", prospects)

                account = _json_get(f"{base_url}/api/runs/{run['id']}/accounts/acme.example")
                self.assertEqual(account["company"]["company"], "Acme Fleet")
                self.assertEqual(account["workflow"]["status"], "Exported")
                self.assertGreaterEqual(len(account["role_groups"]), 1)
                self.assertGreaterEqual(len(account["outreach_drafts"]), 1)
                self.assertEqual(account["evidence_timeline"][0]["title"], "About")
                self.assertIn("lead_state.updated", {item["action"] for item in account["audit_events"]})

                feedback = _json_post(
                    f"{base_url}/api/runs/{run['id']}/quality-feedback",
                    {
                        "domain": "acme.example",
                        "company": "Acme Fleet",
                        "dimension": "outreach",
                        "rating": "positive",
                        "note": "Message angle fits the evidence.",
                    },
                )
                self.assertEqual(feedback["feedback"]["dimension"], "outreach")
                self.assertEqual(feedback["summary"]["rating_counts"]["positive"], 1)

                feedback_listing = _json_get(f"{base_url}/api/runs/{run['id']}/quality-feedback")
                self.assertEqual(feedback_listing["summary"]["total"], 1)
                account_with_feedback = _json_get(f"{base_url}/api/runs/{run['id']}/accounts/acme.example")
                self.assertEqual(account_with_feedback["quality_summary"]["total"], 1)
                self.assertEqual(account_with_feedback["quality_feedback"][0]["note"], "Message angle fits the evidence.")

                feedback_csv = _text_get(f"{base_url}/api/runs/{run['id']}/quality-feedback.csv")
                self.assertIn("run_id,company,domain,dimension,rating", feedback_csv)
                self.assertIn("Message angle fits the evidence.", feedback_csv)

                outreach_listing = _json_get(f"{base_url}/api/runs/{run['id']}/outreach-drafts")
                self.assertGreaterEqual(outreach_listing["summary"]["total"], 1)
                outreach_status = _json_post(
                    f"{base_url}/api/runs/{run['id']}/outreach-drafts/status",
                    {
                        "prospect_id": outreach_listing["drafts"][0]["prospect_id"],
                        "domain": "acme.example",
                        "company": "Acme Fleet",
                        "status": "Approved",
                        "note": "Approved for first sequence.",
                    },
                )
                self.assertEqual(outreach_status["outreach_status"]["status"], "Approved")
                self.assertEqual(outreach_status["account_summary"]["status_counts"]["Approved"], 1)
                outreach_csv = _text_get(f"{base_url}/api/runs/{run['id']}/outreach-drafts.csv")
                self.assertIn("subject,body,cta", outreach_csv)
                self.assertIn("Approved for first sequence.", outreach_csv)

                eval_cases = _json_get(f"{base_url}/api/evals/cases")
                self.assertGreaterEqual(len(eval_cases["cases"]), 1)
                eval_run = _json_post(f"{base_url}/api/evals/runs", {"run_id": run["id"]})
                self.assertEqual(eval_run["eval_run"]["run_id"], run["id"])
                self.assertIn(eval_run["eval_run"]["status"], {"passed", "needs_review"})
                eval_listing = _json_get(f"{base_url}/api/evals/runs")
                self.assertEqual(eval_listing["summary"]["total"], 1)
                eval_csv = _text_get(f"{base_url}/api/evals/runs.csv")
                self.assertIn("metric_name,metric_value", eval_csv)

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

    def test_scheduled_expansion_run_scans_due_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.ensure()
            source = store.save_source(
                "Expansion manual source",
                source_type="manual_seed",
                value="Mojio, moj.io\nAutomate, automate.co.za",
                source_group="test-expansion",
                schedule="daily",
            )
            store.sources_path.write_text(json.dumps([source], indent=2, sort_keys=True), encoding="utf-8")
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            app = GTMApp(store=store, pipeline=pipeline)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                state = _json_get(f"{base_url}/api/state")
                self.assertEqual(state["source_coverage"]["due_source_count"], 1)

                expansion = _json_post(
                    f"{base_url}/api/expansion/run",
                    {"due_only": True, "max_companies": 5},
                )
                self.assertEqual(expansion["run"]["status"], "completed")
                self.assertEqual(expansion["run"]["source_count"], 1)
                self.assertEqual(expansion["run"]["scanned_source_count"], 1)
                self.assertEqual(expansion["run"]["candidate_count"], 2)
                self.assertEqual(expansion["run"]["source_results"][0]["source_name"], "Expansion manual source")
                self.assertEqual(expansion["coverage"]["due_source_count"], 0)
                self.assertEqual(expansion["coverage"]["latest_expansion_run"]["id"], expansion["run"]["id"])
                self.assertEqual(expansion["scans"][-1]["candidate_count"], 2)

                runs = _json_get(f"{base_url}/api/expansion/runs")
                self.assertEqual(runs["runs"][-1]["id"], expansion["run"]["id"])

                repeat = _json_post(f"{base_url}/api/expansion/run", {"due_only": True, "max_companies": 5})
                self.assertEqual(repeat["run"]["status"], "empty")
                self.assertEqual(repeat["run"]["source_count"], 0)

                audit = _json_get(f"{base_url}/api/audit-log")
                self.assertIn("expansion.run", {item["action"] for item in audit["events"]})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_provider_budget_denial_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStore(Path(tmp))
            store.ensure()
            store.settings_path.write_text(
                json.dumps(
                    {
                        "provider_limits": {
                            "enabled": True,
                            "daily": {"search": 100},
                            "rate_per_minute": {"search": 100},
                            "per_run": {"max_companies": 1},
                        }
                    }
                ),
                encoding="utf-8",
            )
            pipeline = ResearchPipeline(store, evidence_fetcher=fake_evidence)
            app = GTMApp(store=store, pipeline=pipeline)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                with self.assertRaises(HTTPError) as denied:
                    _json_post(
                        f"{base_url}/api/search",
                        {
                            "query": "",
                            "seed_text": "Acme Fleet, acme.example",
                            "max_companies": 2,
                        },
                    )
                self.assertEqual(denied.exception.code, 429)
                body = json.loads(denied.exception.read().decode("utf-8"))
                self.assertIn("provider_control", body)
                self.assertEqual(body["provider_control"]["action"], "search")
                self.assertEqual(body["provider_control"]["limit_type"], "per_run")
                self.assertIn("max_companies", body["error"])

                health = _json_get(f"{base_url}/api/health")
                self.assertEqual(health["provider_controls"]["denied_counts"]["search"], 1)
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
