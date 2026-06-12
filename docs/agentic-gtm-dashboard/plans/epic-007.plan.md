# Epic 007 Plan: Public Source Intelligence Hardening

## Objective

Improve company intelligence collection before PR/live deployment by attaching public profile and resource URLs from search results, website outbound links, and metadata summaries to the correct lead records and K2 documents.

## Requirements Covered

- Search internet for companies.
- Scrape websites, GitHub, LinkedIn, and other public resources for company data.
- Present discovered companies, personas, and metadata in the dashboard.
- Support K2 natural-language research with heavy metadata usage.

## Scope

- Associate LinkedIn, GitHub, social, marketplace/review, and other public-resource search results with discovered company domains.
- Preserve typed public source-reference buckets in saved run metadata.
- Expose intelligence coverage and typed refs in the lead detail UI.
- Include source-reference metadata in K2 account-summary documents.
- Add regression coverage for discovery association, metadata classification, and K2 metadata export.

## Non-Goals

- Authenticated LinkedIn scraping.
- Paid search provider integration.
- Live Cloudflare deploy or live K2 upload.

## Tasks

### T-001 Search Result Profile Association

- Update discovery candidate construction so profile/resource result URLs are collected across the search page even after the company-domain limit is reached.
- Match public refs back to candidates by company/domain tokens.
- Preserve GitHub, LinkedIn, and other resource URLs on `DiscoveryCandidate`.

### T-002 Typed Source Metadata

- Extend source-reference normalization with social, marketplace/review, careers, contact, and other buckets.
- Add public profile/resource counts and intelligence coverage flags.

### T-003 Dashboard And K2 Exposure

- Render typed refs and coverage flags in the lead detail Source Metadata section.
- Add source-reference URL lists and counts to K2 account-summary documents.
- Preserve `other_urls` in API search responses and saved run candidates.

### T-004 Tests And Validation

- Add focused tests for search-result association, typed metadata, and K2 metadata keys.
- Run the full local test and syntax/deployment dry-run checks.

## Validation

- `python3 -m unittest tests.test_discovery tests.test_metadata tests.test_k2_sync tests.test_research tests.test_web`
- `python3 -m unittest discover -s tests` (38 tests)
- `python3 -m py_compile icp_engine/*.py deployment/cloudflare/render_wrangler_config.py`
- `node --check icp_engine/web_assets/app.js`
- `node --check deployment/cloudflare/worker.js`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`
- `git diff --check`
- Secret-fragment scan for provided Cloudflare/K2/Apollo values
