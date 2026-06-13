# Knowledge2 ICP Qualification Engine

This repo scores company lists against the incumbent-software ICP in `icp.md`.

It is designed for Knowledge² outbound and design-partner qualification:
mature B2B/B2B2C software companies with proprietary workflow/data assets,
enough scale to feel AI pressure, and limited public AI traction.

## Quick start

```bash
python3 -m icp_engine.cli qualify --input examples/companies.csv --out out
```

Outputs:

- `out/ranked_companies.csv`
- `out/dossier.md`
- `out/cache/` with fetched public pages

## Agentic GTM dashboard

Start the local web app:

```bash
python3 -m icp_engine.web --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

The dashboard can:

- discover company candidates from a search query, committed seeds, manual seeds,
  and optional Serper/Apollo company search
- fetch public website evidence and reuse the existing ICP scoring engine
- inspect ranked leads, hard gates, evidence, strategy, and recommended personas
- inspect and export Apollo-backed prospects or strategy persona targets
- start from a committed 428-account seed universe with Volaris/Harris
  Constellation portfolio companies, named ICP examples from `icp.md`, and
  the qualified 100-company data run under `data/`
- edit the active ICP criteria markdown in local app state
- ask natural language questions over stored run evidence and metadata
- manage saved discovery sources for SERP queries, portfolio URLs, and manual
  seed lists, then scan them into candidate previews
- optionally call Apollo and GitHub providers when environment variables are configured

Set `SERPER_API_KEY` or `SERP_API_KEY` to use Google SERP discovery through
Serper. Without it, local Python falls back to DuckDuckGo HTML search and the
Cloudflare Worker falls back to Apollo company search when `APOLLO_API_KEY` is
configured, then to seeded/manual candidates.

Local app state is stored under `out/app_state` by default and is ignored by git.

For protected local API access, set an admin token before starting the server
and save the same token in the dashboard sidebar:

```bash
export ICP_ADMIN_TOKEN=$(openssl rand -hex 24)
python3 -m icp_engine.web --host 127.0.0.1 --port 8765
```

The API can run without a token only on loopback hosts by default. Public or
container binds such as `0.0.0.0` require `ICP_ADMIN_TOKEN` unless
`--allow-open-api` or `ICP_ALLOW_OPEN_API=true` is set for an isolated local
network.

K2 sync is dry-run by default:

```bash
python3 -m icp_engine.k2_sync --run-id <run-id> --state-dir out/app_state
```

The K2-native ICP workspace bootstrap can create the five ICP corpora,
seed/index them, and ensure the ICP agents, feeds, and PipelineSpec:

```bash
K2_API_KEY=<k2-token> K2_BASE_URL=https://api-dev.knowledge2.ai \
  python3 -m icp_engine.k2_workspace \
  --project-name "Knowledge2 ICP GTM Dev" \
  --apply-uploads --apply-indexes --apply-primitives --health-check
```

The Research tab answers from local run evidence by default. After a live K2
sync applies and stores a `corpus_id` on the run, or when `K2_RESEARCH_CORPUS_ID`
is configured, research requests use K2 generation with a `run_id` metadata
filter and fall back to local evidence search when K2 is unavailable.

Prospect exports are available from the dashboard Prospects tab or API:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/prospects
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/prospects.csv
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/accounts/<domain>
```

Saved discovery sources are available from the Sources tab or API. Source scans
reuse the configured search provider for SERP-style sources and parse manual
seed lists without calling external providers:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/sources
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Portfolio sweep","type":"serp_query","value":"vertical market software portfolio companies workflow data","schedule":"weekly"}' \
  http://127.0.0.1:8765/api/sources
```

Provider budget and rate-limit controls are seeded in app settings and are
reported from `/api/state` and detailed `/api/health`. Search, source scans,
runs, Apollo enrichment, research, and K2 sync actions are audited under
`provider_action.allowed` or `provider_action.denied`; denied actions return
HTTP `429` with a `provider_control` payload describing the limit.

Lead workflow state is stored under `out/app_state` and survives server
restarts. API clients can mark leads as `New`, `Review`, `Qualified`,
`Rejected`, or `Exported`, bulk update lead status, save filtered lead views,
and read the audit log:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domain":"moj.io","status":"Qualified","note":"Ready for outreach"}' \
  http://127.0.0.1:8765/api/runs/<run-id>/lead-state

curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/workflow
```

Operators can also label recommendation quality for score fit, persona fit,
and outreach usefulness. Feedback appears in account drilldowns, aggregate
state summaries, and can be exported as CSV for eval or K2 feedback pipelines:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domain":"moj.io","dimension":"score","rating":"positive","note":"Strong workflow-data fit"}' \
  http://127.0.0.1:8765/api/runs/<run-id>/quality-feedback

curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/quality-feedback.csv
```

Health checks:

```bash
curl -sS http://127.0.0.1:8765/healthz
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/health
```

Cloudflare Worker validation:

```bash
wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml
```

The Worker serves the dashboard assets and seeded dashboard API directly. It
uses the `ICP_STATE` KV binding to persist criteria edits, saved sources/scans,
provider usage, runtime runs, lead workflow states, and quality feedback across
Worker isolates. It does not require a local tunnel or a separate
`ICP_API_ORIGIN`.

For a live environment, render an ignored Wrangler config from environment
variables instead of editing committed placeholders:

```bash
export CLOUDFLARE_ACCOUNT_ID=<account-id>
export ICP_CLOUDFLARE_ROUTE=gtm-dev.knowledge2.ai
make cloudflare-dry-run
```

## Input CSV

Required:

- `company`
- `domain`

Optional:

- `category`
- `founded_year`
- `employee_count`
- `hq`
- `notes`

## Gemini-assisted scoring

Gemini is optional. Without credentials, the engine uses deterministic rules.

To enable Gemini through Vertex AI:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=global
export GEMINI_MODEL=gemini-3.5-flash
export GEMINI_THINKING_BUDGET=0
python3 -m icp_engine.cli qualify --input companies.csv --out out --use-gemini
```

The model only classifies public evidence snippets. Local scoring validates and
clamps all model output.

This repo defaults to `gemini-3.5-flash` with `GEMINI_THINKING_BUDGET=0` for
minimal thinking/low-latency classification.

## Validate

```bash
python3 -m unittest discover -s tests
python3 -m pip install '.[e2e]'
python3 -m playwright install chromium
make e2e-smoke
python3 -m icp_engine.cli qualify --input examples/companies.csv --out out --no-fetch
```

With deployment environment variables exported, also run:

```bash
make cloudflare-preflight
```

## Docs

- `docs/SCORING.md`: hard gates, posture rubric, and tiering
- `docs/GEMINI.md`: Vertex AI / Gemini service-account setup
- `docs/OPERATIONS.md`: common local runbooks
- `docs/CLOUDFLARE_K2_DEPLOYMENT.md`: Cloudflare, K2, Apollo deployment path
- `docs/designs/2026-06-13-icp-eval-pipeline.md`: K2-first eval pipeline
  design for loaded data and produced GTM results
