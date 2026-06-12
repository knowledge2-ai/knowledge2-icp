# Cloudflare Worker Shell

This directory contains the deploy shell for hosting the Agentic GTM dashboard on
Cloudflare Workers with static assets and an API proxy.

## Shape

- Static dashboard assets are uploaded from `../../icp_engine/web_assets`.
- `/healthz` returns public edge liveness metadata.
- `/api/*` requests are proxied to `ICP_API_ORIGIN`.
- `/api/*` requests require `ICP_ADMIN_TOKEN` and
  `Authorization: Bearer <token>`; the Worker fails closed if the edge token is
  missing.
- Secrets are declared by name only in `wrangler.toml`.

Cloudflare's current Workers static assets configuration uses an `assets`
directory in the Wrangler config. The optional assets binding lets Worker code
fetch assets through `env.ASSETS.fetch()`.

## Local Preview

```bash
cd deployment/cloudflare
export ICP_ADMIN_TOKEN=$(openssl rand -hex 24)
ICP_API_ORIGIN=http://127.0.0.1:8765 wrangler dev
```

Then check:

```bash
curl -sS http://127.0.0.1:8787/healthz
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8787/api/health
```

## Secret Setup

Do not put token values in `wrangler.toml`.

```bash
cd deployment/cloudflare
wrangler secret put K2_API_KEY
wrangler secret put APOLLO_API_KEY
wrangler secret put ICP_ADMIN_TOKEN
```

Use the same `ICP_ADMIN_TOKEN` value on the origin service so the Worker and
Python API enforce the same boundary. Do not use the Cloudflare API token as the
dashboard admin token.

## Render Environment Config

The committed `wrangler.toml` keeps placeholders so account IDs and API origins
do not drift into source control. Render an ignored deploy config from
environment variables:

```bash
cd ../..
export CLOUDFLARE_ACCOUNT_ID=<account-id>
export ICP_API_ORIGIN=https://<api-origin>
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
export ICP_API_ORIGIN=https://<api-origin>
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

Before production, set `ICP_API_ORIGIN` to the API origin that runs the Python
scoring/research service or a future Worker-native API implementation. The
current route is a proposed development custom domain: `gtm-dev.knowledge2.ai`.
