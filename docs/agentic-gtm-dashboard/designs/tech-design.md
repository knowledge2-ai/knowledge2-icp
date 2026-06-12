# Agentic GTM Dashboard Technical Design

## Current State

The repo is a Python package with a CLI that reads company CSV input, fetches public website evidence, optionally classifies snippets with Gemini, scores companies using the ICP rubric from `icp.md`, and writes CSV/Markdown reports. There is no web server, persistence layer, admin UI, search provider abstraction, Apollo integration, K2 integration, or deployment configuration.

## Target Architecture

The first implementation slice adds a local Python web application around the current engine:

- `icp_engine.web`: standard-library HTTP server and JSON API.
- `icp_engine.app_store`: JSON-backed state store under `out/app_state` by default.
- `icp_engine.discovery`: web-search candidate discovery with parser-testable provider functions.
- `icp_engine.research`: orchestration pipeline that runs discovery, website evidence fetch, optional GitHub/Apollo metadata, scoring, strategy generation, and persistence.
- `icp_engine.strategy`: persona and outreach strategy rules derived from tier, vertical, score components, and evidence signals.
- `icp_engine.apollo`: optional Apollo adapter using the official People Search and Organization Search endpoint shapes.
- `icp_engine.k2_backend`: metadata-first export/sync abstraction for future Knowledge2 corpus ingestion and natural-language retrieval.
- `icp_engine/web_assets`: dashboard HTML/CSS/JS served by the local web server.

## API Surface

- `GET /`: dashboard.
- `GET /api/state`: current criteria, runs, provider status, and selected run summary.
- `POST /api/criteria`: persist edited criteria markdown to app state.
- `POST /api/search`: discover candidate companies from a query.
- `POST /api/runs`: create a full research run from query and/or manual company seeds.
- `GET /api/runs/{run_id}`: detailed run payload.
- `POST /api/research`: natural-language question over stored run metadata and evidence.

## Data Model

- Run: id, query, created_at, status, provider warnings, criteria snapshot hash, leads.
- Lead: company input, score result, strategy, personas, evidence, external metadata.
- External metadata: GitHub URLs/repo hints, LinkedIn URLs, Apollo organizations/people, K2 sync status.
- Criteria: active markdown, source path, updated_at.

## K2 Plan

The local app stores evidence with stable metadata keys: `run_id`, `company`, `domain`, `source_type`, `source_url`, `evidence_id`, `tier`, `score`, and ICP dimensions. This is the contract needed to upload documents to K2 corpora and later issue K2-backed search/generate requests. The local natural-language endpoint uses the same metadata shape so the UI and API do not need to change when the retrieval backend moves from local JSON to K2.

## Apollo Plan

Apollo is optional and configured by `APOLLO_API_KEY`. The first adapter supports:

- Organization Search: `POST https://api.apollo.io/api/v1/mixed_companies/search`.
- People Search: `POST https://api.apollo.io/api/v1/mixed_people/api_search`.

The dashboard displays prospect/persona candidates when available. Without a key, the app generates persona recommendations from ICP strategy rules.

## Cloudflare Plan

The Python server is the local control plane for the first slice. Production can be split into:

- Cloudflare Pages or Workers frontend on a K2 subdomain.
- Cloudflare Workers API facade for search/run creation.
- Durable Objects or D1 for run state.
- R2 for evidence/cache artifacts.
- Worker secrets for `K2_API_KEY`, `APOLLO_API_KEY`, model keys, and search provider keys.

The repo will include docs and environment names without committing tokens.

## Security Considerations

- Do not commit user-provided tokens.
- Treat external URLs as untrusted; fetch with timeouts and bounded response sizes.
- Do not perform authenticated LinkedIn scraping.
- Make admin criteria editing local-only in the first slice; production requires auth before exposing it.
- Store generated app state under ignored output paths unless explicitly exported.

## UX Direction

The first dashboard should be a dense GTM operations tool:

- Search/run controls in a left rail.
- Ranked lead table with score/tier filters.
- Lead detail panel with hard gates, evidence, personas, and strategy.
- Criteria editor tab.
- Natural-language research panel grounded in stored evidence and metadata.

## Validation

- Unit tests for discovery parsing, strategy generation, state persistence, research orchestration with mocked fetch/search, and API endpoints.
- Existing CLI tests must remain green.
- Manual smoke: start `python3 -m icp_engine.web --port 8765`, load `/`, call `/api/state`, and run a no-fetch or low-page demo run.
