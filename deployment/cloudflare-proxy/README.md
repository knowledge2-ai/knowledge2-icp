# gtm-dev Cloudflare proxy → private Cloud Run

Fronts `gtm-dev.knowledge2.ai` with the `gtm-demo` Cloud Run service (the Python
engine in `ICP_PUBLIC_READ_ONLY` mode). Replaced the self-contained demo worker
that used to live in `deployment/cloudflare/` (retired in #46) — this Worker
holds no app logic; it just gets anonymous browser traffic past Cloud Run's
edge auth.

## Why a token-minting proxy (not allUsers)

`knowledge2-dev-9650` enforces `constraints/iam.allowedPolicyMemberDomains`, so a
Cloud Run service **cannot** be granted to `allUsers` — the public-invoker grant
is rejected org-wide (`icp-gtm` is private for the same reason). Public access
therefore has to come through a fronting layer that authenticates as a real
principal. This Worker mints a Google-signed **ID token** (audience = the Cloud
Run URL) from a service-account key in Worker secrets and attaches it to every
upstream request. The service account holds `roles/run.invoker` on `gtm-demo`.

Writes stay blocked regardless: the engine runs read-only, so even though the
Worker can reach every route, mutations return 401 at the app layer.

## One-time setup (you run these — they touch credentials)

These steps create a service account and a key. **I can't run them** — they mint
and handle a private key. Run them yourself (`!`-prefix in the session is fine).

```bash
DEV=knowledge2-dev-9650
SA=gtm-demo-invoker

# 1. Service account + run.invoker on the demo service only.
gcloud iam service-accounts create "$SA" --project "$DEV" \
  --display-name "gtm-dev Cloudflare proxy invoker"
gcloud run services add-iam-policy-binding gtm-demo \
  --project "$DEV" --region=us-central1 \
  --member="serviceAccount:${SA}@${DEV}.iam.gserviceaccount.com" \
  --role=roles/run.invoker

# 2. Create a key (sensitive — do not commit or paste it anywhere).
gcloud iam service-accounts keys create /tmp/gtm-demo-sa.json \
  --project "$DEV" \
  --iam-account "${SA}@${DEV}.iam.gserviceaccount.com"
```

Then load the key into Worker secrets (values are read from the JSON; nothing is
echoed to the terminal):

```bash
cd deployment/cloudflare-proxy
jq -r .client_email   /tmp/gtm-demo-sa.json | wrangler secret put GCP_SA_EMAIL
jq -r .private_key    /tmp/gtm-demo-sa.json | wrangler secret put GCP_SA_PRIVATE_KEY
jq -r .private_key_id /tmp/gtm-demo-sa.json | wrangler secret put GCP_SA_PRIVATE_KEY_ID
shred -u /tmp/gtm-demo-sa.json   # or: rm -P on macOS
```

## Deploy + cut over

```bash
wrangler deploy        # publishes gtm-dev-proxy, claims the gtm-dev custom domain
```

`wrangler.toml` binds `gtm-dev.knowledge2.ai` as a **custom domain** on this
Worker (`custom_domain = true`). Publishing it makes Cloudflare reassign the
hostname from the old demo worker to this one and manage the DNS record + edge
cert itself — so this proxy no longer depends on the old worker's DNS record.
Verify before retiring anything:

```bash
curl -s https://gtm-dev.knowledge2.ai/api/health | jq '{version, public_read_only}'
# expect: version "0.1.0" (engine, not "0.1.0-worker") and public_read_only true
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://gtm-dev.knowledge2.ai/api/criteria -d '{}'   # expect 401
```

**Rollback:** `wrangler rollback` reverts this Worker to its previous version,
or revert the route binding. To restore the old demo worker (its source was
removed from the repo in #46), `git revert` the retirement PR to bring back
`deployment/cloudflare/`, then re-publish it on the `gtm-dev` route.

## Retire the old worker (#46) — done

`deployment/cloudflare/` is removed from the repo and the live worker
`knowledge2-icp-gtm-dashboard` is deleted from Cloudflare.

Order mattered: the old worker held the `gtm-dev.knowledge2.ai` custom domain,
which owned the only proxied DNS record for the host, and the bare-route proxy
rode on that record — so deleting the worker first would have taken gtm-dev
offline. The fix was to make this proxy own the hostname before deleting:

```bash
wrangler deploy        # proxy claims gtm-dev as a custom domain (reassigns DNS)
# verified version 0.1.0 / public_read_only true and writes 401 on the live host
wrangler delete --name knowledge2-icp-gtm-dashboard   # now a true orphan
# re-verified the live host stayed healthy after the delete
```

## Notes

- The ID token is cached in-isolate and refreshed ~60s before its 1h expiry.
- Rotate the key periodically: create a new key, `wrangler secret put` the three
  values, then delete the old key with `gcloud iam service-accounts keys delete`.
- Key handling is yours end to end — the key never enters the repo or my output.
