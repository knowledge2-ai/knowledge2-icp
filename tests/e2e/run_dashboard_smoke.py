from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from icp_engine.app_store import AppStore
from icp_engine.models import CompanyInput, Evidence
from icp_engine.research import ResearchPipeline


DEFAULT_MANIFEST = Path(__file__).with_name("e2e.manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Agentic GTM dashboard browser smoke test.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to e2e.manifest.json.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium headed for debugging.")
    args = parser.parse_args()

    manifest = _load_manifest(Path(args.manifest))
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        print("Playwright is required for E2E smoke tests. Install with: python3 -m pip install '.[e2e]'", file=sys.stderr)
        return 2

    app = manifest["application"]
    host = str(app.get("host") or "127.0.0.1")
    port = _available_port(int(app.get("port") or 9876))
    base_url = f"http://{host}:{port}"
    artifact_dir = ROOT / str(manifest.get("validation", {}).get("artifactDir") or "out/e2e")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="knowledge2-icp-e2e-") as state_dir:
        process = _start_server(host, port, Path(state_dir))
        try:
            _wait_for_health(base_url, str(app.get("healthCheckPath") or "/healthz"), int(app.get("startTimeoutSeconds") or 15))
            run = _seed_run(Path(state_dir))
            console_errors: list[str] = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=not args.headed and bool(manifest.get("execution", {}).get("headless", True)))
                context = browser.new_context(viewport=manifest.get("execution", {}).get("viewport") or {"width": 1440, "height": 980})
                page = context.new_page()
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                timeout = int(manifest.get("execution", {}).get("timeoutMs") or 10000)

                page.goto(base_url, wait_until="domcontentloaded", timeout=timeout)
                expect(page.get_by_role("heading", name="Lead Discovery Dashboard")).to_be_visible(timeout=timeout)
                expect(page.locator("#lead-rows .lead-row")).to_contain_text("Mojio", timeout=timeout)
                page.locator("#lead-page-size").select_option("25")
                expect(page.locator("#lead-pagination")).to_contain_text("of 1", timeout=timeout)
                page.locator("#lead-sort-field").select_option("company")
                page.locator("#lead-sort-direction").click()
                mojio_row = page.locator("#lead-rows .lead-row").filter(has_text="Mojio").first
                mojio_row.locator(".lead-select").check()
                page.locator("#bulk-status").select_option("Review")
                page.locator("#bulk-note").fill("Smoke queue review")
                page.locator("#bulk-update-leads").click()
                expect(mojio_row).to_contain_text("Review", timeout=timeout)
                page.locator("#lead-view-name").fill("Smoke review queue")
                page.locator("#save-lead-view").click()
                expect(page.locator("#lead-view-select")).to_contain_text("Smoke review queue", timeout=timeout)

                page.locator("button.tab[data-view='sources']").click()
                expect(page.locator("#source-list")).to_contain_text("Portfolio expansion SERP", timeout=timeout)
                expect(page.locator("#expansion-panel")).to_contain_text("Scheduled Source Sweeps", timeout=timeout)
                expect(page.locator("#run-expansion")).to_be_visible(timeout=timeout)
                page.locator("#source-name").fill("Smoke manual source")
                page.locator("#source-type").select_option("manual_seed")
                page.locator("#source-schedule").select_option("weekly")
                page.locator("#source-group").fill("smoke")
                page.locator("#source-value").fill("Mojio, moj.io\nAutomate, automate.co.za")
                page.locator("#source-form button[type='submit']").click()
                expect(page.locator("#source-list")).to_contain_text("Smoke manual source", timeout=timeout)
                page.locator("#source-list .source-item").filter(has_text="Smoke manual source").get_by_role("button", name="Scan").click()
                expect(page.locator("#source-scan-detail")).to_contain_text("Mojio", timeout=timeout)
                page.locator("#use-source-candidates").click()
                expect(page.locator("#candidate-panel")).to_contain_text("Mojio", timeout=timeout)

                page.locator("#lead-rows .lead-row").filter(has_text="Mojio").first.click()
                expect(page.locator("#view-prospects")).to_be_visible(timeout=timeout)
                expect(page.locator("#prospect-rows .prospect-company-node").first).to_contain_text("Mojio", timeout=timeout)
                expect(page.locator("#prospect-rows .prospect-role-group").first).to_contain_text("primary", timeout=timeout)
                expect(page.locator("#prospect-rows .prospect-row").first).to_contain_text("Mojio", timeout=timeout)
                expect(page.locator("#account-drilldown .account-title")).to_contain_text("Mojio", timeout=timeout)
                expect(page.locator("#account-drilldown .account-role-tree")).to_contain_text("VP Engineering", timeout=timeout)
                expect(page.locator("#account-drilldown .outreach-card")).to_contain_text("Outreach Drafts", timeout=timeout)
                expect(page.locator("#account-drilldown .outreach-draft").first).to_contain_text("AI workflow opportunity map", timeout=timeout)
                expect(page.locator("#account-drilldown .evidence-timeline")).to_contain_text("Platform", timeout=timeout)
                expect(page.locator("#account-workflow-form")).to_be_visible(timeout=timeout)

                page.locator("button.tab[data-view='research']").click()
                page.locator("#research-question").fill("Which lead has workflow API evidence and who should we contact?")
                page.locator("#research-form button[type='submit']").click()
                expect(page.locator(".research-answer-text")).to_contain_text("Recommended GTM motion", timeout=timeout)
                expect(page.locator("#research-answer")).to_contain_text("Metadata Used", timeout=timeout)
                expect(page.locator("#research-answer")).to_contain_text("VP Engineering", timeout=timeout)
                expect(page.locator("#research-answer")).to_contain_text("Citations", timeout=timeout)

                page.locator("button.tab[data-view='k2']").click()
                page.locator("#k2-workspace-status").click()
                expect(page.locator("#k2-panel")).to_contain_text("K2 Workspace", timeout=timeout)
                expect(page.locator("#k2-panel")).to_contain_text("ICP Source Corpus", timeout=timeout)
                page.locator("#k2-preview").click()
                expect(page.locator("#k2-panel .manifest-preview")).to_contain_text("source_type", timeout=timeout)

                page.locator("button.tab[data-view='evals']").click()
                page.locator("#run-eval").click()
                expect(page.locator("#eval-panel")).to_contain_text("Quality Metrics", timeout=timeout)
                expect(page.locator("#eval-panel")).to_contain_text("K2 Alignment", timeout=timeout)

                page.locator("button.tab[data-view='setup']").click()
                expect(page.locator("#setup-grid")).to_contain_text("Discovery query", timeout=timeout)
                expect(page.locator("#setup-grid")).to_contain_text("Mojio", timeout=timeout)
                expect(page.locator("#setup-grid")).to_contain_text("Advanced Utility Systems", timeout=timeout)
                expect(page.locator("#setup-grid")).to_contain_text("cloudflare-seeded-worker", timeout=timeout)
                expect(page.locator("#settings-form")).to_be_visible(timeout=timeout)
                page.locator("#settings-default-query").fill("smoke workflow data weak AI positioning")
                page.locator("#settings-max-companies").fill("43")
                page.locator("#settings-limit-daily-search").fill("19")
                page.locator("#settings-save").click()
                expect(page.locator("#settings-status")).to_contain_text("Settings saved.", timeout=timeout)

                page.locator("button.tab[data-view='criteria']").click()
                expect(page.locator("#criteria-markdown")).not_to_be_empty(timeout=timeout)
                expect(page.locator("#criteria-format")).to_be_visible(timeout=timeout)
                expect(page.locator("#criteria-lint")).to_be_visible(timeout=timeout)
                expect(page.locator("#criteria-version-select")).to_be_visible(timeout=timeout)
                page.locator("#criteria-lint").click()
                expect(page.locator("#criteria-lint-panel")).to_contain_text("warnings", timeout=timeout)
                page.locator("#criteria-impact").click()
                expect(page.locator("#criteria-impact-panel")).to_contain_text("Changed", timeout=timeout)
                page.locator("#criteria-markdown").fill("# Smoke ICP  \n* Gate")
                page.locator("#criteria-format").click()
                expect(page.locator("#criteria-markdown")).to_have_value("# Smoke ICP\n- Gate\n", timeout=timeout)
                page.locator("#criteria-undo").click()
                expect(page.locator("#criteria-markdown")).to_have_value("# Smoke ICP  \n* Gate", timeout=timeout)
                page.locator("#criteria-redo").click()
                expect(page.locator("#criteria-markdown")).to_have_value("# Smoke ICP\n- Gate\n", timeout=timeout)

                context.close()
                browser.close()

            research = _post_json(
                f"{base_url}/api/research",
                {"run_id": run["id"], "question": "Which lead has workflow API evidence and who should we contact?"},
            )
            account = _json_get(f"{base_url}/api/runs/{run['id']}/accounts/moj.io")
            state = _json_get(f"{base_url}/api/state")
            _assert(state.get("prompts"), "Expected seeded prompts in API state.")
            _assert(state.get("settings", {}).get("max_companies") == 43, "Expected settings editor persistence.")
            _assert(state.get("settings", {}).get("deployment_mode") == "cloudflare-seeded-worker", "Expected seeded deployment mode.")
            _assert(state.get("lists", {}).get("account_universe"), "Expected seeded account universe list.")
            _assert(state.get("sources"), "Expected seeded source library.")
            _assert(state.get("source_coverage", {}).get("source_count", 0) >= 3, "Expected source coverage summary.")
            _assert(research.get("provider") == "local", "Expected local research provider for isolated E2E smoke.")
            _assert(research.get("metadata_used", {}).get("persona_titles"), "Expected metadata_used persona titles.")
            _assert(research.get("citations"), "Expected research citations.")
            _assert(account.get("role_groups"), "Expected account detail role groups.")
            _assert(account.get("outreach_drafts"), "Expected account detail outreach drafts.")
            _assert(account.get("evidence_timeline"), "Expected account detail evidence timeline.")
            _assert(state.get("eval_summary", {}).get("latest_status") in {"passed", "needs_review"}, "Expected latest eval status.")
            _assert(not console_errors, f"Browser console errors: {console_errors}")

            report = {
                "status": "passed",
                "base_url": base_url,
                "run_id": run["id"],
                "validations": ["ui", "api", "console"],
                "matched_leads": research.get("matched_leads", []),
                "citation_count": len(research.get("citations", [])),
            }
            (artifact_dir / "dashboard-smoke-report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            print(f"E2E smoke passed: {artifact_dir / 'dashboard-smoke-report.json'}")
            return 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _available_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(host: str, port: int, state_dir: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    command = [
        sys.executable,
        "-m",
        "icp_engine.web",
        "--host",
        host,
        "--port",
        str(port),
        "--state-dir",
        str(state_dir),
    ]
    return subprocess.Popen(command, cwd=ROOT, env=env, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_for_health(base_url: str, health_path: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    url = f"{base_url}{health_path}"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"Server did not become healthy at {url}: {last_error}")


def _seed_run(state_dir: Path) -> dict[str, Any]:
    store = AppStore(state_dir)
    pipeline = ResearchPipeline(store, evidence_fetcher=_fake_evidence)
    return pipeline.create_run(query="", seed_text="Mojio, moj.io", include_github=False, use_apollo=False)


def _fake_evidence(company: CompanyInput, cache_dir: Path) -> tuple[list[Evidence], list[str]]:
    return (
        [
            Evidence(
                evidence_id="e1",
                url=f"https://{company.domain}/platform",
                title="Platform",
                text=(
                    "Founded in 2012. Enterprise software platform for fleet workflow, dispatch, "
                    "telematics records, integrations, API, permissions, analytics, and customer operations. "
                    "Trusted by customers and partners. Contact sales@example.com."
                ),
                metadata={
                    "page_category": "product",
                    "links": [
                        "https://www.linkedin.com/company/mojio",
                        "https://github.com/mojio",
                        f"https://{company.domain}/docs/api",
                    ],
                    "external_links": ["https://github.com/mojio"],
                },
            )
        ],
        [],
    )


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _json_get(url: str) -> dict[str, Any]:
    request = Request(url)
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    raise SystemExit(main())
