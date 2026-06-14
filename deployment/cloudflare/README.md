# Cloudflare Worker Shell

This directory contains the Cloudflare Workers deployment for the Agentic GTM
dashboard.

## Shape

- Static dashboard assets are uploaded from `../../icp_engine/web_assets`.
- `/healthz` returns public edge liveness metadata.
- `/api/*` requests are served by the Worker from committed seed defaults plus
  the `ICP_STATE` KV namespace for mutable dashboard state.
- `/api/health`, `/api/auth/session`, and read-only demo data endpoints are
  public. Mutating actions, provider runs, exports, K2 sync, and admin
  diagnostics require `ICP_ADMIN_TOKEN` or a short-lived session token minted by
  `/api/auth/session`.
- Search expands from the committed seed pack through `SERPER_API_KEY` /
  `SERP_API_KEY` when configured, or Apollo company search when only
  `APOLLO_API_KEY` is configured.
- The dashboard shows seeded/read-only leads without a session. It exchanges
  `ICP_ADMIN_TOKEN` for an eight-hour browser session before edits, provider
  runs, exports, K2 sync, or admin diagnostics; the raw admin token is not stored
  in browser localStorage.
- Secrets are declared by name only in `wrangler.toml`.
- Criteria edits, saved sources/scans, provider usage, runtime runs, lead
  workflow states, and quality feedback are persisted in KV.
- The K2 tab can dry-run manifest export without K2. With `K2_API_KEY`
  configured, `Apply sync` uploads the generated seed/runtime manifest to K2.

Cloudflare's current Workers static assets configuration uses an `assets`
directory in the Wrangler config. The optional assets binding lets Worker code
fetch assets through `env.ASSETS.fetch()`.

## Auth scope matrix

The Worker enforces `public_read_only: true` — read-only demo data is served
without a token, while everything that mutates state or touches admin/provider
surfaces requires `ICP_ADMIN_TOKEN` or a session token from `/api/auth/session`.
The authoritative allowlist is `isPublicReadRequest()` in `worker.js`; this table
mirrors it.

| Route | Method | Access |
| --- | --- | --- |
| `/healthz` | GET | Public (edge liveness) |
| `/api/health` | GET | Public |
| `/api/auth/session` | POST | Public (mints a session from `ICP_ADMIN_TOKEN`) |
| `/api/state` | GET | Public read |
| `/api/sources` | GET | Public read |
| `/api/expansion/runs` | GET | Public read |
| `/api/criteria/versions` | GET | Public read |
| `/api/runs/{id}` | GET | Public read |
| `/api/runs/{id}/workflow` | GET | Public read |
| `/api/runs/{id}/prospects` | GET | Public read |
| `/api/runs/{id}/accounts/{key}` | GET | Public read |
| `/api/workspace-state` | GET | Protected (admin diagnostics) |
| All non-GET `/api/*` (settings, sources, runs, exports, K2 sync, …) | POST/PUT/DELETE | Protected (mutations, provider runs, exports, `k2_apply_sync`) |
| Any other `/api/*` GET not listed above | GET | Protected |

The frozen-Worker durability test
(`tests/test_cloudflare_worker_runtime.py`) asserts this contract: public reads
return `200`, mutations without a token return `401`.

## Local Preview

```bash
cd deployment/cloudflare
wrangler dev
```

Then check:

```bash
curl -sS http://127.0.0.1:8787/healthz
curl -sS http://127.0.0.1:8787/api/health
curl -sS -X POST http://127.0.0.1:8787/api/auth/session \
  -H 'content-type: application/json' \
  -d '{"token":"<dashboard-admin-token>"}'
```

## Secret Setup

Do not put token values in `wrangler.toml`.

```bash
cd deployment/cloudflare
wrangler secret put K2_API_KEY
wrangler secret put APOLLO_API_KEY
wrangler secret put ICP_ADMIN_TOKEN
wrangler secret put SERPER_API_KEY
```

`SERPER_API_KEY` is optional. Without it, the Worker uses Apollo company search
for live expansion when `APOLLO_API_KEY` is present and otherwise searches the
committed seed pack plus manual seed text.

Do not use the Cloudflare API token as the dashboard admin token.

## Render Environment Config

The committed `wrangler.toml` keeps placeholders so account IDs and routes do
not drift into source control. Render an ignored deploy config from
environment variables:

```bash
cd ../..
export CLOUDFLARE_ACCOUNT_ID=<account-id>
export ICP_CLOUDFLARE_ROUTE=gtm-dev.knowledge2.ai
make cloudflare-config
```

This writes `deployment/cloudflare/wrangler.generated.toml`, which is ignored by
git and can be passed to Wrangler.

## Deploy Preflight

Run a sanitized preflight before any live deploy. The preflight checks required
environment variables, Wrangler availability, and generated config validity
without printing token values:

```bash
export CLOUDFLARE_ACCOUNT_ID=<account-id>
export CLOUDFLARE_API_TOKEN=<api-token>
export ICP_CLOUDFLARE_ROUTE=gtm-dev.knowledge2.ai
export ICP_ADMIN_TOKEN=<dashboard-admin-token>
export K2_API_KEY=<k2-api-key>
export APOLLO_API_KEY=<apollo-api-key>
make cloudflare-preflight
```

## Deploy

```bash
wrangler deploy --config deployment/cloudflare/wrangler.generated.toml
```

The current route is a development custom domain: `gtm-dev.knowledge2.ai`.
