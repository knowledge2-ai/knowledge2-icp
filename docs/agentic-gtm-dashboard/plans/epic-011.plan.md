# Epic 011 Plan: Metadata-Backed Research Briefs

## Objective

Make the natural-language Research tab useful even before a live K2 corpus is configured by returning structured GTM research briefs from stored evidence, criteria, personas, and metadata.

## Requirements Covered

- Have a natural-language interface to do in-depth research.
- Use heavy metadata based on K2-style document metadata.
- Present discovered companies and target personas in a dashboard.
- Preserve K2-backed generation as the preferred live path when a corpus is available.

## Scope

- Keep live K2 generation behavior unchanged when a run has a corpus ID or `K2_RESEARCH_CORPUS_ID`.
- Upgrade the local fallback answer from terse lead summaries to a structured GTM brief.
- Include strategy, recommended motion, first step, personas, criteria profile, source coverage, signal tags, matched leads, and source mix in the answer.
- Return `metadata_used` with signal, source, category, coverage, persona, and criteria tags.
- Enrich citations with source type, page category, and signal tags.
- Render multiline answers, metadata chips, matched leads, and citation tags in the Research tab.
- Recapture the Research screenshot with an answered question.

## Non-Goals

- Live K2 generation execution.
- LLM-based local summarization.
- New browser E2E framework installation.
- Live deployment or PR creation.

## Tasks

### T-001 Local Research Brief

- Rank direct evidence and metadata hits.
- Prefer direct evidence over synthetic metadata when relevance is tied.
- Build a concise GTM brief from the strongest matched accounts.

### T-002 Metadata Payload

- Add a structured `metadata_used` payload.
- Include source-aware citation metadata for the dashboard and K2-like provenance.

### T-003 Research UI

- Preserve multiline answer formatting.
- Render metadata-used chips, matched leads, and citation tags.
- Keep the existing K2 provider label behavior.

### T-004 Tests And UX Evidence

- Add research regression assertions for brief shape, metadata tags, persona usage, and citation metadata.
- Update the UX capture scenario to ask a deterministic research question.
- Recapture and compress `03_research.jpg`.

## Validation

- `python3 -m unittest tests.test_research`
- `python3 -m unittest discover -s tests` (46 tests)
- `python3 -m py_compile icp_engine/*.py deployment/cloudflare/render_wrangler_config.py`
- `node --check icp_engine/web_assets/app.js`
- `node --check deployment/cloudflare/worker.js`
- `python3 /Users/antonmishel/.codex/skills/review-ux/scripts/validate_scenarios.py docs/agentic-gtm-dashboard/plans/ui-review-scenarios.json`
- `python3 /Users/antonmishel/.codex/skills/review-ux/scripts/capture_screens.py --scenario docs/agentic-gtm-dashboard/plans/ui-review-scenarios.json`
- `python3 /Users/antonmishel/.codex/skills/review-ux/scripts/compress_images.py --input-dir docs/agentic-gtm-dashboard/designs/screenshots/original`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`
- `git diff --check`
- Secret-fragment scan for provided Cloudflare/K2/Apollo values
- Local smoke: `/healthz` on `http://127.0.0.1:8765`
