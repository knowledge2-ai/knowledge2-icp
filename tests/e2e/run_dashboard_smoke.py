from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
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
    parser.add_argument("--live-base-url", default=os.environ.get("ICP_E2E_LIVE_BASE_URL", ""), help="Run against a deployed dashboard instead of starting a local server.")
    parser.add_argument("--admin-token-env", default="ICP_ADMIN_TOKEN", help="Environment variable containing the admin token for live auth smoke.")
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
    if args.live_base_url:
        admin_token = os.environ.get(args.admin_token_env, "")
        if not admin_token:
            print(f"{args.admin_token_env} is required for --live-base-url.", file=sys.stderr)
            return 2
        return _run_live_auth_smoke(
            manifest,
            args.live_base_url.rstrip("/"),
            admin_token,
            artifact_dir,
            headed=args.headed,
            expect=expect,
            sync_playwright=sync_playwright,
        )

    with tempfile.TemporaryDirectory(prefix="knowledge2-icp-e2e-") as state_dir:
        process = _start_server(host, port, Path(state_dir))
        try:
            _wait_for_health(base_url, str(app.get("healthCheckPath") or "/healthz"), int(app.get("startTimeoutSeconds") or 15))
            run = _seed_run(Path(state_dir))
            csv_source_path = Path(state_dir) / "smoke-sources.csv"
            csv_source_path.write_text("Company,Domain\nMojio,moj.io\nAutomate,automate.co.za\n", encoding="utf-8")
            console_errors: list[str] = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=not args.headed and bool(manifest.get("execution", {}).get("headless", True)))
                context = browser.new_context(viewport=manifest.get("execution", {}).get("viewport") or {"width": 1440, "height": 980})
                # The local smoke server runs in open mode (no admin token), so /api/* is
                # unauthenticated. The admin-only tabs (K2, evals) are gated purely by a
                # client-side session flag; seed one so the diagnostics stages stay reachable.
                context.add_init_script("window.localStorage.setItem('knowledge2.icp.sessionToken', 'e2e-local-session');")
                page = context.new_page()
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                timeout = int(manifest.get("execution", {}).get("timeoutMs") or 10000)

                page.goto(base_url, wait_until="domcontentloaded", timeout=timeout)
                expect(page.get_by_role("heading", name="Lead Discovery Dashboard")).to_be_visible(timeout=timeout)
                expect(page.locator("#lead-rows .lead-row").filter(has_text="Mojio").first).to_contain_text("Mojio", timeout=timeout)
                page.locator("#lead-page-size").select_option("25")
                expect(page.locator("#lead-pagination")).to_contain_text("of 3", timeout=timeout)
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
                page.locator("#source-csv-file").set_input_files(str(csv_source_path))
                expect(page.locator("#source-type")).to_have_value("csv_upload", timeout=timeout)
                expect(page.locator("#source-value")).to_have_value(re.compile("Mojio"), timeout=timeout)
                page.locator("#source-form button[type='submit']").click()
                expect(page.locator("#source-list")).to_contain_text("smoke sources", timeout=timeout)
                page.locator("#source-list .source-item").filter(has_text="smoke sources").get_by_role("button", name="Scan").click()
                expect(page.locator("#source-scan-detail")).to_contain_text("Automate", timeout=timeout)
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
                # The fallback draft now renders the persona-routed template scaffold
                # (workflow-efficiency for the engineering/product personas).
                expect(page.locator("#account-drilldown .outreach-draft").first).to_contain_text("An AI opportunity in Mojio's workflows", timeout=timeout)
                expect(page.locator("#account-drilldown .outreach-draft").first).to_contain_text("Mojio", timeout=timeout)
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
                expect(page.locator("#k2-panel")).to_contain_text("docs", timeout=timeout)
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
                expect(page.locator("#setup-grid")).to_contain_text("Workspace State", timeout=timeout)
                expect(page.locator("#workspace-state-panel")).to_contain_text("local-files", timeout=timeout)
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

                mobile_screenshots = _capture_mobile_screenshots(page, artifact_dir, expect=expect, timeout=timeout)

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
            _validate_outreach_content(account.get("outreach_drafts", []))
            _assert(account.get("evidence_timeline"), "Expected account detail evidence timeline.")
            _assert(state.get("eval_summary", {}).get("latest_status") in {"passed", "needs_review"}, "Expected latest eval status.")
            provider_failure = _expect_provider_failure(base_url)
            _assert(not console_errors, f"Browser console errors: {console_errors}")

            report = {
                "status": "passed",
                "base_url": base_url,
                "run_id": run["id"],
                "validations": ["ui", "api", "console", "outreach-content", "mobile-screenshots", "provider-failure"],
                "matched_leads": research.get("matched_leads", []),
                "citation_count": len(research.get("citations", [])),
                "mobile_screenshots": mobile_screenshots,
                "provider_failure": provider_failure.get("error", ""),
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


def _run_live_auth_smoke(
    manifest: dict[str, Any],
    base_url: str,
    admin_token: str,
    artifact_dir: Path,
    *,
    headed: bool,
    expect: Any,
    sync_playwright: Any,
) -> int:
    timeout = int(manifest.get("execution", {}).get("timeoutMs") or 10000)
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed and bool(manifest.get("execution", {}).get("headless", True)))
        context = browser.new_context(viewport=manifest.get("execution", {}).get("viewport") or {"width": 1440, "height": 980})
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout)
        expect(page.get_by_role("heading", name="Lead Discovery Dashboard")).to_be_visible(timeout=timeout)
        expect(page.locator("#auth-status")).to_contain_text("Admin session", timeout=timeout)
        expect(page.locator("#run-status")).to_contain_text("API token required", timeout=timeout)

        page.locator("#admin-token").fill(admin_token)
        page.locator("#save-admin-token").click()
        expect(page.locator("#auth-status")).to_contain_text("Admin session active", timeout=timeout)
        expect(page.locator("#lead-rows .lead-row").filter(has_text="Mojio").first).to_contain_text("Mojio", timeout=timeout)

        session_token = page.evaluate("localStorage.getItem('knowledge2.icp.sessionToken')")
        legacy_token = page.evaluate("localStorage.getItem('knowledge2.icp.adminToken')")
        _assert(bool(session_token), "Expected browser session token in localStorage.")
        _assert(not legacy_token, "Expected raw legacy admin token to be absent from localStorage.")

        page.locator("button.tab[data-view='k2']").click()
        page.locator("#k2-workspace-status").click()
        expect(page.locator("#k2-panel")).to_contain_text("K2 Workspace", timeout=timeout)
        expect(page.locator("#k2-panel")).to_contain_text("ICP Source Corpus", timeout=timeout)
        expect(page.locator("#k2-panel")).to_contain_text("docs", timeout=timeout)
        page.locator("#k2-pipeline-dry-run").click()
        expect(page.locator("#k2-panel")).to_contain_text("Pipeline Action Result", timeout=max(timeout, 30000))
        expect(page.locator("#k2-panel")).to_contain_text("dry_run", timeout=timeout)

        context.close()
        browser.close()

    headers = {"Authorization": f"Bearer {session_token}", "User-Agent": "Mozilla/5.0 Knowledge2ICPE2E/1.0"}
    health = _json_get(f"{base_url}/api/health", headers={"User-Agent": headers["User-Agent"]})
    state = _json_get(f"{base_url}/api/state", headers=headers)
    workspace = _json_get(f"{base_url}/api/k2-workspace", headers=headers)
    _assert(health.get("auth_required") is True, "Expected live /api/health to require auth.")
    _assert(health.get("authenticated") is False, "Expected public live /api/health request to be unauthenticated.")
    _assert(state.get("lists", {}).get("account_universe"), "Expected live state account universe.")
    _assert(workspace.get("source") == "k2_api", "Expected live K2 workspace status from K2 API.")
    _assert(workspace.get("project", {}).get("status") == "found", "Expected live K2 project to be found.")
    pipeline_action = _post_json(f"{base_url}/api/k2-workspace/pipeline", {"action": "dry_run"}, headers=headers)
    _assert(pipeline_action.get("status") == "ok", "Expected live K2 pipeline dry-run to succeed.")
    _assert(pipeline_action.get("pipeline_spec", {}).get("status") == "found", "Expected live K2 pipeline spec to be found.")
    corpus_counts = {
        item.get("key"): item.get("health", {}).get("total_documents")
        for item in workspace.get("corpora", [])
    }
    _assert(corpus_counts and all((count or 0) > 0 for count in corpus_counts.values()), "Expected live K2 corpus document counts.")
    unexpected_console_errors = [message for message in console_errors if "status of 401" not in message]
    _assert(not unexpected_console_errors, f"Browser console errors: {unexpected_console_errors}")

    report = {
        "status": "passed",
        "base_url": base_url,
        "validations": ["ui", "api", "storage", "k2"],
        "k2_pipeline_action": pipeline_action.get("action"),
        "account_count": len(state.get("lists", {}).get("account_universe", [])),
        "k2_source": workspace.get("source"),
        "k2_project_status": workspace.get("project", {}).get("status"),
        "corpus_counts": corpus_counts,
    }
    report_path = artifact_dir / "dashboard-live-auth-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Live auth E2E smoke passed: {report_path}")
    return 0


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
    # Seed >= _SUBSTANTIVE_RUN_LEADS (3) companies so the dashboard lands on this
    # user run rather than the 424-lead seeded showcase (app_store _default_landing_run_id).
    return pipeline.create_run(
        query="",
        seed_text="Mojio, moj.io\nAutomate, automate.co.za\nDispatch, dispatch.me",
        include_github=False,
        use_apollo=False,
    )


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


def _capture_mobile_screenshots(page: Any, artifact_dir: Path, *, expect: Any, timeout: int) -> list[str]:
    page.set_viewport_size({"width": 390, "height": 844})
    screenshots: list[str] = []
    for view in ("leads", "prospects", "k2", "criteria"):
        page.locator(f"button.tab[data-view='{view}']").click()
        expect(page.locator(f"#view-{view}")).to_be_visible(timeout=timeout)
        path = artifact_dir / f"mobile-{view}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(str(path.relative_to(ROOT)))
    return screenshots


def _validate_outreach_content(drafts: list[dict[str, Any]]) -> None:
    """Content validation for the recency-aware template scaffold (offline path).

    With no Anthropic key the deterministic fallback renders the persona-routed
    template, so this stage asserts the content is real: template variety across
    personas, grounded in the seeded evidence, and no unrendered merge fields.
    """
    _assert(len(drafts) >= 2, "Expected multiple outreach drafts for the account.")
    subjects = [str(draft.get("subject") or "") for draft in drafts]
    # Persona routing produces template variety: the engineering/product persona
    # lands on workflow-efficiency, the chief-level persona on exec-ai-urgency.
    _assert(
        any("An AI opportunity in" in subject for subject in subjects),
        f"Expected a workflow-efficiency subject; got {subjects}.",
    )
    _assert(
        any("turning your workflow data into an AI edge" in subject for subject in subjects),
        f"Expected an exec-ai-urgency subject; got {subjects}.",
    )
    for draft in drafts:
        subject = str(draft.get("subject") or "")
        body = str(draft.get("body") or "")
        cta = str(draft.get("cta") or "")
        label = draft.get("persona") or draft.get("title") or "?"
        _assert(bool(subject), f"Empty outreach subject for {label}.")
        _assert(bool(cta), f"Empty outreach CTA for {label}.")
        _assert("Mojio" in body, f"Outreach body for {label} is not grounded in the company.")
        _assert("Platform" in body, f"Outreach body for {label} does not cite the seeded evidence.")
        _assert("{" not in body and "{" not in subject, f"Unrendered merge field leaked for {label}.")


def _expect_provider_failure(base_url: str) -> dict[str, Any]:
    _post_json(
        f"{base_url}/api/settings",
        {
            "provider_limits": {
                "daily": {"search": 100},
                "rate_per_minute": {"search": 100},
                "per_run": {"max_companies": 1},
            }
        },
    )
    try:
        _post_json(f"{base_url}/api/search", {"query": "fleet workflow software", "max_companies": 3})
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        _assert(exc.code == 429, f"Expected provider failure 429, got {exc.code}.")
        _assert(payload.get("provider_control"), "Expected provider failure to include provider_control.")
        return payload
    raise AssertionError("Expected provider budget failure for /api/search.")


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=body, method="POST", headers=request_headers)
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _json_get(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    raise SystemExit(main())
