# Operations

## Install

```bash
make setup
```

## Run Rules-Only

```bash
python3 -m icp_engine.cli qualify \
  --input examples/companies.csv \
  --out out/rules \
  --no-fetch
```

## Run With Domain Enrichment

```bash
python3 -m icp_engine.cli qualify \
  --input examples/companies.csv \
  --out out/enriched
```

## Run With Gemini

```bash
set -a
. ./.env
set +a
.venv/bin/python -m icp_engine.cli qualify \
  --input examples/companies.csv \
  --out out/gemini \
  --use-gemini
```

## Outputs

- `ranked_companies.csv`: sortable qualification table
- `dossier.md`: human-readable company dossiers
- `cache/`: fetched public page snippets used for repeatable scoring

## Run Agentic GTM Dashboard

```bash
python3 -m icp_engine.web --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

Useful local settings:

```bash
export ICP_APP_STATE_DIR=out/app_state
export ICP_CRITERIA_PATH=icp.md
export ICP_ADMIN_TOKEN=
export ICP_ALLOW_OPEN_API=false
export APOLLO_API_KEY=
export K2_API_KEY=
export K2_RESEARCH_CORPUS_ID=
export GITHUB_TOKEN=
```

Leave optional provider keys blank for deterministic local testing. The dashboard
will still score manual seed companies and public website evidence.
Leave `ICP_ADMIN_TOKEN` blank only for loopback local open mode. When it is set,
every `/api/*` request requires `Authorization: Bearer $ICP_ADMIN_TOKEN`; save
the same token in the dashboard sidebar before running searches. Non-loopback
binds such as `0.0.0.0` require `ICP_ADMIN_TOKEN` unless
`ICP_ALLOW_OPEN_API=true` or `--allow-open-api` is used for an isolated local
network.

Useful API checks:

```bash
curl -sS http://127.0.0.1:8765/healthz
curl -sS http://127.0.0.1:8765/api/state
curl -sS http://127.0.0.1:8765/api/health
curl -sS http://127.0.0.1:8765/api/runs/{run_id}/prospects
curl -sS http://127.0.0.1:8765/api/runs/{run_id}/prospects.csv
curl -sS http://127.0.0.1:8765/api/runs/{run_id}/k2-manifest
curl -sS -X POST http://127.0.0.1:8765/api/runs/{run_id}/k2-export
```

Browser smoke validation:

```bash
python3 -m pip install '.[e2e]'
python3 -m playwright install chromium
make e2e-smoke
```

The smoke runner starts its own isolated local server and writes a report to
`out/e2e/dashboard-smoke-report.json`; it does not use live provider secrets.

Deployment preflight:

```bash
make cloudflare-preflight
```

This validates required deploy environment variables and generated Wrangler
config shape without printing secret values.

With API protection enabled:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/state
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/health
```

The prospect endpoints return Apollo people when `APOLLO_API_KEY` is configured
and strategy persona targets when Apollo is disabled or has no matching people.

The K2 export writes `out/app_state/k2_manifests/{run_id}.json` by default.
Research answers use local stored evidence unless the run has a synced K2
`corpus_id` or `K2_RESEARCH_CORPUS_ID` is configured; in that case the app calls
K2 generation with the run's metadata filter and shows K2 citations in the
Research tab.

Dry-run a K2 upload from local state:

```bash
python3 -m icp_engine.k2_sync --run-id {run_id} --state-dir out/app_state
```

Apply a live K2 upload only after setting `K2_API_KEY`:

```bash
export K2_API_KEY=...
python3 -m icp_engine.k2_sync \
  --run-id {run_id} \
  --state-dir out/app_state \
  --project-name "Knowledge2 ICP GTM" \
  --corpus-name "ICP Run {run_id}" \
  --apply
```

Cloudflare shell validation:

```bash
wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml
```

## Security Notes

- Never commit `.secrets/`, `.env`, or generated output under `out/`.
- Service-account keys should be rotated if shared beyond the local operator.
- Prefer a short-lived key or workload identity when moving this into automation.
