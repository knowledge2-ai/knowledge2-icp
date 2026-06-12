# Epic 008 Plan: Candidate Preview And Search Refinement

## Objective

Add a refinement step between discovery and scoring so GTM operators can inspect discovered candidate companies, deselect weak fits, and run enrichment/scoring only for selected accounts.

## Requirements Covered

- Search internet for companies.
- Provide a nice web interface to inspect results and refine the search.
- Preserve collected source/profile metadata while producing scored leads and personas.

## Scope

- Use the existing `POST /api/search` endpoint from the dashboard.
- Render discovered candidates with checkboxes in the Discover sidebar.
- Submit selected candidate objects directly to `POST /api/runs`.
- Preserve discovered source URLs, GitHub URLs, LinkedIn URLs, and other refs when creating the run.
- Add tests for selected-candidate run creation through both pipeline and HTTP API.

## Non-Goals

- Browser E2E framework installation.
- Multi-run bulk queueing.
- Saved candidate lists independent of research runs.

## Tasks

### T-001 Pipeline Selected Candidate Contract

- Extend `ResearchPipeline.create_run` to accept candidate payloads.
- Normalize selected candidate domains and dedupe by domain.
- Preserve candidate source/profile refs into run metadata.

### T-002 API Wiring

- Allow `POST /api/runs` to accept a `candidates` array.
- Keep the existing query/seed discovery path when no candidate array is provided.

### T-003 Dashboard Preview UX

- Add a `Preview candidates` control to the Discover form.
- Render checkbox candidate rows with company, domain, source title, and ref count.
- Use checked candidates for the research run when a preview is active.
- Clear stale previews when search inputs change.

### T-004 Tests And Validation

- Add pipeline and HTTP API regression tests for selected candidates.
- Validate JavaScript syntax and full local test suite.

## Validation

- `python3 -m unittest tests.test_research tests.test_web tests.test_discovery`
- `python3 -m unittest discover -s tests` (40 tests)
- `python3 -m py_compile icp_engine/*.py deployment/cloudflare/render_wrangler_config.py`
- `node --check icp_engine/web_assets/app.js`
- `node --check deployment/cloudflare/worker.js`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`
- `git diff --check`
- Secret-fragment scan for provided Cloudflare/K2/Apollo values
- Local smoke: `/api/search` preview and selected-candidate `/api/runs` on `http://127.0.0.1:8765`
- Rendered UX capture: `docs/agentic-gtm-dashboard/designs/screenshots/original/07_candidate_preview.jpg`
