# Cloudflare Worker Shell

This directory contains the Cloudflare Workers deployment for the Agentic GTM
dashboard.

## Shape

- Static dashboard assets are uploaded from `../../icp_engine/web_assets`.
- `/healthz` returns public edge liveness metadata.
- `/api/*` requests are served by the Worker from committed seed defaults.
- Read-only dashboard data, search, run creation, criteria edits, research,
  prospects, CSV export, and K2 dry-runs work without a token.
- Search expands from the committed seed pack through `SERPER_API_KEY` /
  `SERP_API_KEY` when configured, or Apollo company search when only
  `APOLLO_API_KEY` is configured.
- K2 apply sync requires `ICP_ADMIN_TOKEN` and `Authorization: Bearer <token>`.
- Secrets are declared by name only in `wrangler.toml`.
- The K2 tab can dry-run manifest export without K2. With `K2_API_KEY`
  configured, `Apply sync` uploads the generated seed/runtime manifest to K2.

Cloudflare's current Workers static assets configuration uses an `assets`
directory in the Wrangler config. The optional assets binding lets Worker code
fetch assets through `env.ASSETS.fetch()`.

## Local Preview

```bash
cd deployment/cloudflare
wrangler dev
```

Then check:

```bash
curl -sS http://127.0.0.1:8787/healthz
curl -sS http://127.0.0.1:8787/api/state
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
