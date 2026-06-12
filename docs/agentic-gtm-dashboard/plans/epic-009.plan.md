# Epic 009 Plan: Active Criteria Scoring Profile

## Objective

Make the active criteria markdown operational by parsing it into a deterministic scoring profile that influences lead tiering, budget gates, vertical priority signals, lead detail UI, and K2 metadata.

## Requirements Covered

- Qualify by repo ICP criteria.
- Provide an admin UI to configure criteria markdown/prompt.
- Produce a lead list with potential score and strategy.
- Use heavy metadata so K2-backed research can answer how an account was qualified.

## Scope

- Parse active criteria markdown from app state or `icp.md`.
- Extract tier thresholds, employee-count budget range, and priority terms.
- Apply the profile during `ResearchPipeline.create_run` scoring.
- Store the profile in run metadata and each lead's metadata.
- Surface active criteria in the lead detail panel.
- Include criteria profile fields in K2 account summary metadata.
- Add regression tests for parsing, scoring behavior, and run metadata.

## Non-Goals

- Full natural-language criteria interpretation.
- Rewriting the source `icp.md` from the dashboard.
- Live K2 upload or Cloudflare deployment.
- Browser E2E framework installation.

## Tasks

### T-001 Criteria Profile Parser

- Add a small parser for threshold, employee range, and priority-term signals.
- Preserve safe defaults when criteria text omits a field.
- Return warnings for unusual profile values.

### T-002 Scoring Integration

- Pass the active profile into company scoring.
- Use profile tier thresholds for A/B/C tiering.
- Use profile employee range in budget hard gates and budget points.
- Use profile priority terms in rules-based qualification.

### T-003 Metadata And UI

- Persist the profile on each run and lead.
- Add profile fields to K2 account summaries.
- Render active criteria in the lead detail panel without adding visual clutter.

### T-004 Tests And Validation

- Add parser/scoring regression tests.
- Add run metadata tests for criteria hash/profile propagation.
- Recapture the Leads screen with the active criteria panel visible.

## Validation

- `python3 -m unittest tests.test_criteria tests.test_research tests.test_strategy tests.test_k2_sync`
- `python3 -m unittest discover -s tests` (44 tests)
- `python3 -m py_compile icp_engine/*.py deployment/cloudflare/render_wrangler_config.py`
- `node --check icp_engine/web_assets/app.js`
- `node --check deployment/cloudflare/worker.js`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`
- `git diff --check`
- Secret-fragment scan for provided Cloudflare/K2/Apollo values
- Local smoke: `/healthz` on `http://127.0.0.1:8765`
- Rendered UX capture: `docs/agentic-gtm-dashboard/designs/screenshots/original/01_leads.jpg`
