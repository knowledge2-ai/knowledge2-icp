# Epic 012 Plan: Browser E2E Smoke Validation

## Objective

Add a repeatable browser-level smoke test so the dashboard can be validated as a rendered application before PR or deployment, not only through unit tests and screenshot capture.

## Requirements Covered

- Have a nice web interface to inspect results and refine search.
- Present discovered companies and personas in a dashboard.
- Provide natural-language research over evidence and metadata.
- Improve production readiness before Cloudflare/K2 deployment.

## Scope

- Add a manifest-driven E2E configuration under `tests/e2e/`.
- Add a concise E2E test plan documenting route/tab coverage.
- Add a Python Playwright smoke runner that fits the existing Python-only app.
- Start an isolated local `icp_engine.web` server with a temporary state directory.
- Seed deterministic lead evidence through the application layer.
- Exercise rendered Leads, Prospects, Research, K2, and Criteria surfaces.
- Validate `/api/research` output and browser console errors.
- Add a `make e2e-smoke` target.

## Non-Goals

- Full TypeScript Playwright framework.
- CI workflow wiring.
- Mobile, auth-on, failure-state, or visual-regression coverage.
- Live Cloudflare/K2 deployment.

## Tasks

### T-001 E2E Manifest And Plan

- Add `tests/e2e/e2e.manifest.json` with application, seed, execution, and validation settings.
- Add a coverage matrix for the smoke path.

### T-002 Browser Smoke Runner

- Start an isolated local server on an available port.
- Seed a deterministic run with evidence, metadata, strategy, personas, and K2 manifest data.
- Validate the rendered dashboard tabs with Playwright.
- Validate research output via API and check for console errors.

### T-003 Makefile And Dependencies

- Add `make e2e-smoke`.
- Add an optional `e2e` dependency group for Playwright.

## Validation

- `make e2e-smoke`
- `python3 -m py_compile tests/e2e/run_dashboard_smoke.py`
- `python3 -m unittest discover -s tests` (46 tests)
- `python3 -m py_compile icp_engine/*.py deployment/cloudflare/render_wrangler_config.py`
- `node --check icp_engine/web_assets/app.js`
- `node --check deployment/cloudflare/worker.js`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`
- `git diff --check`
- Secret-fragment scan for provided Cloudflare/K2/Apollo values
- Local smoke: `/healthz` on `http://127.0.0.1:8765`
