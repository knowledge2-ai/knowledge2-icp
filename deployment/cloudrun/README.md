# Cloud Run deployment — Python GTM engine

Replaces the Cloudflare `worker.js` (a hand-maintained JS re-implementation of
`icp_engine/web.py`) with the real Python engine running on Cloud Run. One
engine instead of two; the worker becomes dead weight once `gtm-dev` points
here.

## Why this is low-risk to package

- **Zero third-party deps.** `pyproject` has `dependencies = []`; every import in
  `icp_engine/` is stdlib (`ssl` is the only thing beyond the obvious, also
  stdlib). No `requirements.txt`, no lockfile, no native build.
- **Serves its own SPA.** `icp_engine/web_assets/` (644K: `index.html`,
  `app.js`, `styles.css`, `seed-companies.json`) is served by the engine at `/`
  and `/assets/*`. No separate frontend deploy.
- **Demo data is code-resident.** The seeded run (`run-seeded-icp`, 424 leads)
  lives in `icp_engine/seed_defaults.py` + `icp_engine/tenants/knowledge2/`.
  `list_runs()` always prepends it and `load_run()` returns it for the seed id,
  so it survives Cloud Run's **ephemeral filesystem with no persistent disk**.
  User-created runs are ephemeral (lost on restart/scale-to-zero) — acceptable
  for a read-only demo; the read-only mode blocks creating them anyway.

## Route parity (worker vs engine)

The engine is a **strict superset** of the worker — nothing drops at cutover.
Audited the legacy worker (`deployment/cloudflare/worker.js`, retired in #46)
against `icp_engine/web.py`:

- Every worker `/api/*` route exists in the engine.
- Engine-only extras the worker never had: `/api/audit-log`,
  `/api/criteria/suggest`, `/api/evals/runs.csv`, `/api/mining/lookalikes`,
  `/api/mining/profiles`.
- The worker's `/api/v1` "route" is a false match — it's the Apollo base URL
  (`api.apollo.io/api/v1`), not a served path.

## The one behavioral gap: read-only public demo

This is the only place the worker does something the engine does not.

- **Worker** runs as a public read-only demo: GET reads flow, every write
  returns `503 "ICP_ADMIN_TOKEN is required"`. Its public-read allowlist
  (`isPublicReadRequest`, worker.js:4098) is exactly these GETs:
  `/api/state`, `/api/sources`, `/api/expansion/runs`,
  `/api/criteria/versions`, `/api/runs/{id}`, `/api/runs/{id}/workflow`,
  `/api/runs/{id}/prospects`, `/api/runs/{id}/accounts/{a}`.
- **Engine** has only two states (`_authorize_api`, web.py:868):
  - no `ICP_ADMIN_TOKEN` → **all** `/api` open (reads *and* writes), or
  - token set → **all** `/api` gated (reads *and* writes need the token).
  There is no "reads open, writes blocked" mode.

So the engine has no faithful equivalent of the worker's demo. Three ways to
close it — `deploy.sh AUTH=` selects between them:

| `AUTH=`    | Behavior                                   | Matches worker? | Cost |
|------------|--------------------------------------------|-----------------|------|
| `readonly` | public GET allowlist, writes 503           | ✅ yes          | needs a small code change in `web.py` (port `isPublicReadRequest`, gated on `ICP_PUBLIC_READ_ONLY`) |
| `open`     | `ICP_ALLOW_OPEN_API=true`, reads+writes public | ❌ writable/vandalizable | none |
| `token`    | `ICP_ADMIN_TOKEN` gates everything         | ❌ not a public demo | none |
| `access`   | behind Cloudflare Access SSO; full read-write to any verified email in `ICP_ACCESS_TRUSTED_DOMAIN` | ❌ internal tool, not a public demo | needs the Access + Google SSO setup in `deployment/cloudflare-proxy/ACCESS_SSO.md` |

`readonly` is the faithful cutover and the only one that preserves the current
gtm-dev experience. It's a contained change: add an `ICP_PUBLIC_READ_ONLY` env
flag and have `_authorize_api` return `True` for GETs on the allowlist above,
`False` (→ 503/401) otherwise, regardless of token. **Pending the auth-model
decision before implementing.**

## Build & deploy

`deploy.sh` wraps Cloud Build + `gcloud run deploy`. It has **no default
project** and refuses `ams-prod-488315` (prod). Secrets never upload:
`gcloud builds submit` falls back to `.gitignore` (which covers `.env`, `out/`,
`.venv`, `.secrets/`) since there's no `.gcloudignore`.

```bash
# after the target + auth model are confirmed:
PROJECT=<dev-project> REGION=us-central1 SERVICE=gtm-engine-dev AUTH=readonly \
  ./deployment/cloudrun/deploy.sh
```

The Dockerfile lives in this subdir; its ignore file is `Dockerfile.dockerignore`
(BuildKit's adjacent-file convention — a plain `.dockerignore` in a subdir is
ignored). `cloudbuild.yaml` builds from the repo root with `-f` so `icp_engine/`
is reachable.

## Cutover & rollback (tasks #44 → #45 → #46)

1. **#44 stand up** — `deploy.sh` to the dev project. Smoke test the service URL:
   `GET /healthz`, `GET /api/health`, `GET /api/state`, load the SPA, open the
   seeded run, confirm a write is blocked (when `AUTH=readonly`).
2. **#45 repoint** — map `gtm-dev.knowledge2.ai` to the Cloud Run service
   (domain mapping or the existing DNS/proxy). Verify the live host serves the
   same checks. **Rollback:** the worker still exists and still serves the same
   hostname config — repoint DNS back to the worker. Nothing is deleted in this
   step, so rollback is a DNS change only.
3. **#46 retire worker** — repo side done (`deployment/cloudflare/` dropped).
   The live worker (`knowledge2-icp-gtm-dashboard`) is deleted only *after*
   `gtm-dev-proxy` claims `gtm-dev.knowledge2.ai` as its own custom domain — the
   old worker owned the host's DNS record, so deleting it before the proxy owns
   the domain would take gtm-dev offline. See `deployment/cloudflare-proxy/README.md`
   for the safe deploy-then-delete sequence. This is the irreversible step, done last.

## Not done here

- No DNS/domain change (that's #45, needs the console/credentials).
- No `gcloud run deploy` executed (needs the confirmed target + auth model).
- The `ICP_PUBLIC_READ_ONLY` code change is described, not yet written —
  pending the auth-model decision.
