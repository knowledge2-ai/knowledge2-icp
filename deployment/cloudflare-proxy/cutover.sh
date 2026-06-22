#!/usr/bin/env bash
# One-time #45 cutover: load the gtm-demo invoker key into Worker secrets and
# deploy the gtm-dev proxy so gtm-dev.knowledge2.ai fronts the private Cloud Run
# service. Re-runnable. The SA + run.invoker grant + key already exist (created
# earlier); this only sets secrets, deploys, cleans up the key, and verifies.
#
# Run it:  bash deployment/cloudflare-proxy/cutover.sh
set -euo pipefail

KEY="${KEY:-/tmp/gtm-demo-sa.json}"
HOST="${HOST:-gtm-dev.knowledge2.ai}"

# Always operate from this script's own dir, where wrangler.toml (name =
# gtm-dev-proxy) lives — that is what fixes "Required Worker name missing".
cd "$(dirname "${BASH_SOURCE[0]}")"

# wrangler only auto-loads .env from its CWD, and we just cd'd into this subdir,
# so pull the Cloudflare creds from the repo-root .env ourselves. The token here
# is account-scoped (no user context), so wrangler MUST be handed
# CLOUDFLARE_ACCOUNT_ID — otherwise it tries a user/membership lookup the token
# can't make and the 403 surfaces as the opaque "auth error 10000" on deploy.
# Values are exported, never printed.
ENV_FILE="$(cd ../.. && pwd)/.env"
if [[ -f "$ENV_FILE" ]]; then
  for var in CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID; do
    if [[ -z "${!var:-}" ]]; then
      val="$(grep -m1 "^${var}=" "$ENV_FILE" | cut -d= -f2- | tr -d "\"' ")"
      [[ -n "$val" ]] && export "$var=$val"
    fi
  done
fi

command -v jq >/dev/null       || { echo "jq not found — brew install jq" >&2; exit 1; }
command -v wrangler >/dev/null || { echo "wrangler not found — npm i -g wrangler" >&2; exit 1; }
[[ -f "$KEY" ]] || {
  echo "key file $KEY not found." >&2
  echo "recreate it (does NOT touch the existing SA/grant):" >&2
  echo "  gcloud iam service-accounts keys create $KEY --project knowledge2-dev-9650 \\" >&2
  echo "    --iam-account gtm-demo-invoker@knowledge2-dev-9650.iam.gserviceaccount.com" >&2
  exit 1
}

echo "==> Cloudflare account:"
wrangler whoami || { echo "not logged in — run: wrangler login" >&2; exit 1; }

# Deploy FIRST so the Worker script exists — secrets can only be attached to a
# script that is already deployed (otherwise the secrets API returns auth error
# 10000). The Worker returns 500 until its secrets are set, a few seconds below.
echo "==> Deploying gtm-dev-proxy (binds $HOST) ..."
wrangler deploy

# Now set the three secrets. Values are piped from the key file straight into
# wrangler — never printed. Each put publishes a new version of the live Worker.
echo "==> Setting Worker secrets (values not shown) ..."
jq -r .client_email   "$KEY" | wrangler secret put GCP_SA_EMAIL
jq -r .private_key    "$KEY" | wrangler secret put GCP_SA_PRIVATE_KEY
jq -r .private_key_id "$KEY" | wrangler secret put GCP_SA_PRIVATE_KEY_ID

# macOS has no `shred`; rm -P overwrites the file before unlinking.
echo "==> Removing local key file ..."
rm -P "$KEY" 2>/dev/null || rm -f "$KEY"

echo "==> Verifying $HOST serves the engine (expect version 0.1.0, public_read_only true):"
curl -s "https://${HOST}/api/health" | jq '{version, public_read_only}'
echo
echo "==> Write should be blocked (expect 401):"
curl -s -o /dev/null -w "POST /api/criteria -> %{http_code}\n" -X POST "https://${HOST}/api/criteria" -d '{}'
