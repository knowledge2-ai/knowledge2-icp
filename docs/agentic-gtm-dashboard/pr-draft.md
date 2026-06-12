# PR Draft: Agentic GTM Dashboard

## Suggested Title

`feat(gtm): add agentic ICP discovery dashboard`

## Summary

- Adds a local-first Agentic GTM web dashboard around the existing ICP scoring engine, with company discovery, public-source intelligence collection, active criteria-profile scoring, strategy/persona recommendations, and admin criteria editing.
- Adds optional Apollo enrichment/prospect exports plus Knowledge2 manifest/export/sync and K2-backed natural-language research paths with rich metadata.
- Adds local metadata-backed GTM research briefs for runs that are not yet synced to a live K2 corpus.
- Promotes discovered public resource refs such as GitHub, G2, Crunchbase, and social URLs into evidence collection where allowed; LinkedIn remains metadata-only unless handled by an approved provider/API.
- Adds Cloudflare Worker hosting shell, generated Wrangler config flow, API auth guardrails, health/readiness probes, rendered UX review artifacts, and deployment documentation without committing real secrets.
- Adds sanitized Cloudflare/K2/Apollo deploy preflight checks that validate environment readiness without printing secret values.
- Adds a manifest-driven Python Playwright browser smoke runner for the dashboard workflow.

## Changes

### New features / enhancements

- Standard-library Python web app and static dashboard UI.
- Search and manual seed discovery flow.
- Candidate preview with checkbox selection before enrichment/scoring.
- Search-result association for public GitHub, LinkedIn, social, marketplace/review, and other company-resource URLs.
- Public resource-ref evidence fetch queue for GitHub, marketplace/review, and social URLs, with explicit LinkedIn skip warnings.
- Local JSON app state for runs and active criteria profiles.
- Lead detail view with score, tier, hard gates, warnings, strategy, active criteria, evidence, typed source metadata, intelligence coverage, and personas.
- Prospects tab with Apollo-backed people when configured and deterministic strategy persona fallback when not configured.
- CSV/JSON prospect export endpoints.
- Natural-language research endpoint over stored run evidence/metadata, with optional live K2 generation when a run has a synced corpus or `K2_RESEARCH_CORPUS_ID` is configured.
- Research tab answer rendering for structured briefs, metadata-used tags, matched leads, and source-aware citations.
- Browser smoke validation for seeded Leads, Prospects, Research, K2 manifest preview, Criteria, API research output, and console-error checks.
- K2 manifest preview/export, K2 dry-run/apply sync endpoint, and K2 sync CLI.
- Public `/healthz` and protected `/api/health` readiness endpoints.
- Optional `ICP_ADMIN_TOKEN` bearer protection for `/api/*`.

### Configuration / infrastructure

- Cloudflare Worker shell serving static assets and proxying `/api/*` to `ICP_API_ORIGIN`.
- Worker edge auth guard and `/healthz` edge liveness endpoint.
- Wrangler base config with placeholders plus an ignored environment-rendered `wrangler.generated.toml` path for dry-run/deploy.
- Sanitized deploy preflight for `CLOUDFLARE_ACCOUNT_ID`, Cloudflare API token env, `ICP_API_ORIGIN`, `ICP_ADMIN_TOKEN`, `K2_API_KEY`, and `APOLLO_API_KEY`.
- `.env.example`, Makefile, README, operations, and deployment docs updated.

### UX / documentation

- Requirements, technical design, epic plans, completion audit, and rendered UX review.
- Playwright-captured screenshots for Leads, Prospects, Research, K2, K2 manifest, and Criteria views.
- Generated wireframes for dashboard, Prospects, K2, and Research/Criteria surfaces.
- Completion audit mapping each original objective item to evidence and remaining live-deployment decisions.

### Tests

- Unit/integration coverage for app store, active criteria parsing/scoring, discovery/profile association, public resource-ref evidence, candidate preview/selective runs, metadata-backed research briefs, strategy, typed source metadata, K2 client/sync/research generation, prospects, Cloudflare config, and web API/auth/health endpoints.
- Browser smoke coverage for the rendered dashboard workflow through `make e2e-smoke`.
- Existing CLI/evidence tests updated for metadata preservation.

## Files Changed

| Module | Files changed | Summary |
|--------|---------------|---------|
| `icp_engine/` | 20 | Web server, discovery/research pipeline, active criteria profile, provider adapters, metadata, strategy, prospects, K2 backend/client/sync, serialization, web assets |
| `tests/` | 15 | Unit, integration, and E2E smoke tests for new app/API/provider/K2/prospect/criteria/dashboard behavior |
| `docs/` | 30 | PRD, tech design, epic plans, UX screenshots/wireframes, operations/deployment docs, completion audit |
| `deployment/` | 4 | Cloudflare Worker, Wrangler config, generated-config helper, deployment README |
| root config/docs | 4 | README, Makefile, `.env.example`, `pyproject.toml` |

## Upstream Sync

- Target branch: `main` because `origin/main` exists and no remote `dev` branch was found.
- Upstream commits merged: not yet checked/merged because the worktree is still dirty.
- Merge conflicts resolved: none yet.

## Testing

- [x] `python3 -m py_compile icp_engine/*.py deployment/cloudflare/render_wrangler_config.py`
- [x] `python3 -m unittest discover -s tests` (46 tests)
- [x] `make e2e-smoke`
- [x] `python3 deployment/cloudflare/preflight.py --skip-wrangler` with dummy placeholder env values
- [x] `node --check icp_engine/web_assets/app.js`
- [x] `node --check deployment/cloudflare/worker.js`
- [x] `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`
- [x] Render `deployment/cloudflare/wrangler.generated.toml` from environment values
- [x] `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`
- [x] `git diff --check`
- [x] Secret substring scan for provided Cloudflare/K2/Apollo values
- [x] Rendered UX screenshots via Playwright scenario capture
- [ ] CI checks after PR creation

## Live Deployment Notes

This PR intentionally does not deploy or apply live K2 ingestion. Before live deployment:

- Confirm target branch (`dev` vs `main`).
- Confirm public hostname/subdomain.
- Confirm API origin.
- Export `CLOUDFLARE_ACCOUNT_ID`, `ICP_API_ORIGIN`, and optionally `ICP_CLOUDFLARE_ROUTE`; then run `make cloudflare-dry-run`.
- Export `CLOUDFLARE_API_TOKEN`, `ICP_ADMIN_TOKEN`, `K2_API_KEY`, and `APOLLO_API_KEY`; then run `make cloudflare-preflight`.
- Configure Cloudflare `ICP_ADMIN_TOKEN`, `K2_API_KEY`, and `APOLLO_API_KEY` as secrets.
- Configure the same `ICP_ADMIN_TOKEN` on the origin.
- Run K2 sync dry-run before any `--apply`.

## Related Issues

N/A.
