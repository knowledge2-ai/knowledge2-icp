# Epic 010 Plan: Public Resource Evidence Collection

## Objective

Promote discovered public resource references into first-class evidence so company qualification, K2 manifests, and natural-language research can use more than same-domain website pages.

## Requirements Covered

- Scrape websites, GitHub, LinkedIn, and other resources to collect company data.
- Collect as much public company metadata as practical within compliant limits.
- Feed heavy metadata and evidence into K2-backed research.
- Preserve source provenance in the lead inspection dashboard.

## Scope

- Accept candidate GitHub, LinkedIn, and other public resource refs in the evidence fetch path.
- Fetch allowed public resource refs early in the page budget.
- Keep LinkedIn URLs as refs and warning metadata rather than attempting authenticated scraping.
- Classify GitHub, social, and marketplace/review URLs distinctly in evidence metadata.
- Ensure selected-candidate resource refs are passed from the dashboard/API run path into enrichment.
- Add regression tests for direct enrichment and pipeline wiring.

## Non-Goals

- Authenticated LinkedIn scraping.
- Browser automation against third-party sites.
- Paid marketplace/provider integrations beyond existing Apollo/K2 seams.
- Live K2 upload or Cloudflare deployment.

## Tasks

### T-001 Enrichment Queue

- Add optional extra public URLs to company evidence collection.
- Prioritize homepage candidates, then external public refs, then remaining same-domain paths.
- Skip LinkedIn fetching with an explicit warning.

### T-002 Source Classification

- Classify GitHub, LinkedIn, social, and marketplace refs as distinct source types.
- Mark external profile/resource pages with a stable page category.

### T-003 Pipeline Wiring

- Pass selected/discovered candidate refs into default evidence fetching.
- Preserve the custom test fetcher contract for deterministic unit tests.

### T-004 Tests And Validation

- Add enrichment tests proving GitHub refs can become evidence and LinkedIn is not fetched.
- Add pipeline tests proving selected refs reach the default fetcher.
- Validate focused tests, full suite, syntax checks, and deployment dry-runs.

## Validation

- `python3 -m unittest tests.test_enrichment tests.test_metadata tests.test_research`
- `python3 -m unittest discover -s tests` (46 tests)
- `python3 -m py_compile icp_engine/*.py deployment/cloudflare/render_wrangler_config.py`
- `node --check icp_engine/web_assets/app.js`
- `node --check deployment/cloudflare/worker.js`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`
- `git diff --check`
- Secret-fragment scan for provided Cloudflare/K2/Apollo values
- Local smoke: `/healthz` on `http://127.0.0.1:8765`
