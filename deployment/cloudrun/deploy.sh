#!/usr/bin/env bash
# Build + deploy the Python GTM engine to Cloud Run.
#
# This script is parameterized and does NOTHING destructive on its own beyond a
# `gcloud run deploy` you trigger explicitly. It will NOT run against a project
# unless you pass PROJECT — there is no default, on purpose (prod is
# ams-prod-488315 and must never be the target here).
#
# Required env / args:
#   PROJECT   GCP project id           (e.g. ams-gtm-dev)        — REQUIRED
#   REGION    Cloud Run region         (default: us-central1)
#   SERVICE   Cloud Run service name   (default: gtm-engine-dev)
#   REPO      Artifact Registry repo   (default: gtm)
#   AUTH      one of: readonly | open | token | access            — REQUIRED
#               readonly : public reads, writes blocked  (needs the read-only
#                          mode in web.py — the parity gap vs the worker)
#               open     : ICP_ALLOW_OPEN_API=true, reads AND writes public
#               token    : ICP_ADMIN_TOKEN gates everything (not a public demo)
#               access   : behind Cloudflare Access SSO; full read-write to any
#                          verified email in ACCESS_DOMAIN (default posterity.ventures)
#   ADMIN_TOKEN   required only when AUTH=token (read from env, never echoed)
#   ACCESS_DOMAIN required only when AUTH=access (default: posterity.ventures)
#
# Example (after you confirm the target):
#   PROJECT=ams-gtm-dev AUTH=readonly ./deployment/cloudrun/deploy.sh
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT to the dev GCP project (NOT ams-prod-488315)}"
REGION="${REGION:-us-central1}"
# Public read-only demo that replaces the Cloudflare worker. NOT icp-gtm — that
# is the separate token-gated, fully-keyed dashboard surface and must be left alone.
SERVICE="${SERVICE:-gtm-demo}"
# Reuse the project's existing Artifact Registry repo (created by prior deploys).
REPO="${REPO:-cloud-run-source-deploy}"
AUTH="${AUTH:?set AUTH=readonly|open|token|access}"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo manual)"

if [[ "$PROJECT" == "ams-prod-488315" ]]; then
  echo "refusing to deploy to prod (ams-prod-488315). Pick the dev project." >&2
  exit 1
fi
if [[ "$SERVICE" == "icp-gtm" ]]; then
  echo "refusing to overwrite icp-gtm (the keyed dashboard). Use a demo service name." >&2
  exit 1
fi

IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/gtm-engine:${TAG}"
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Map AUTH -> the env vars the engine reads. run_server() refuses a non-loopback
# bind unless a token is set OR ICP_ALLOW_OPEN_API is true OR (readonly) the
# read-only demo mode is enabled.
ENV_VARS="ICP_APP_STATE_DIR=/tmp/app_state"
RUN_FLAGS=(--allow-unauthenticated)   # Cloud Run edge auth; app-level auth is separate
case "$AUTH" in
  readonly) ENV_VARS="${ENV_VARS},ICP_PUBLIC_READ_ONLY=true" ;;
  open)     ENV_VARS="${ENV_VARS},ICP_ALLOW_OPEN_API=true" ;;
  token)
    : "${ADMIN_TOKEN:?AUTH=token requires ADMIN_TOKEN in env}"
    ENV_VARS="${ENV_VARS},ICP_ADMIN_TOKEN=${ADMIN_TOKEN}" ;;
  access)
    ENV_VARS="${ENV_VARS},ICP_ACCESS_TRUSTED_DOMAIN=${ACCESS_DOMAIN:-posterity.ventures}" ;;
  *) echo "AUTH must be readonly|open|token|access" >&2; exit 1 ;;
esac

echo "Building ${IMAGE} ..."
gcloud builds submit \
  --project "$PROJECT" \
  --config "${REPO_ROOT}/deployment/cloudrun/cloudbuild.yaml" \
  --substitutions="_IMAGE=${IMAGE}" \
  "$REPO_ROOT"

echo "Deploying ${SERVICE} to ${REGION} (auth=${AUTH}) ..."
gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --image "$IMAGE" \
  --port 8080 \
  --set-env-vars "$ENV_VARS" \
  "${RUN_FLAGS[@]}"

echo "Done. Service URL:"
gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --format='value(status.url)'
