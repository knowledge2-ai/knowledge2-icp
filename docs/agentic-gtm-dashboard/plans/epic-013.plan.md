# Epic 013 Plan: Sanitized Deploy Preflight

## Objective

Make the live Cloudflare/K2/Apollo deployment path safer and more repeatable by adding a preflight command that validates required environment variables and generated Wrangler config without printing secret values.

## Requirements Covered

- Consider hosting on Cloudflare.
- Consider using Knowledge2 as backend.
- Consider using Apollo for enrichment and prospect discovery.
- Consider hosting the application in a K2 subdomain.
- Avoid committing or echoing provided secrets.

## Scope

- Add `deployment/cloudflare/preflight.py`.
- Validate required environment variables for live deploy:
  `CLOUDFLARE_ACCOUNT_ID`, Cloudflare API token env, `ICP_API_ORIGIN`,
  `ICP_ADMIN_TOKEN`, `K2_API_KEY`, and `APOLLO_API_KEY`.
- Warn when `ICP_CLOUDFLARE_ROUTE` is omitted and the default route will be used.
- Reuse the existing Wrangler config renderer to validate account ID, API origin, route, and secret-free generated config shape.
- Add `make cloudflare-preflight`.
- Add unit coverage proving preflight does not print secret values.
- Update deployment docs and PR/audit artifacts.

## Non-Goals

- Running a live Cloudflare deployment.
- Uploading to a live K2 corpus.
- Calling Apollo with live credentials.
- Storing token values in files or generated artifacts.

## Tasks

### T-001 Preflight CLI

- Add a CLI that emits human-readable and optional JSON status.
- Return non-zero when required deploy prerequisites are missing.
- Avoid printing raw secret values.

### T-002 Tests

- Cover success with dummy placeholder env values.
- Cover missing env failures.
- Assert token values are absent from formatted output.

### T-003 Docs

- Document `make cloudflare-preflight` in README, operations, Cloudflare README, deployment checklist, completion audit, and PR draft.

## Validation

- `python3 -m unittest tests.test_cloudflare_config`
- `python3 deployment/cloudflare/preflight.py --skip-wrangler` with dummy placeholder env values
- `python3 -m unittest discover -s tests` (48 tests)
- `make e2e-smoke`
- `python3 -m py_compile icp_engine/*.py deployment/cloudflare/render_wrangler_config.py deployment/cloudflare/preflight.py tests/e2e/run_dashboard_smoke.py`
- `node --check icp_engine/web_assets/app.js`
- `node --check deployment/cloudflare/worker.js`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml`
- `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`
- `git diff --check`
- Secret-fragment scan for provided Cloudflare/K2/Apollo values
- Local smoke: `/healthz` on `http://127.0.0.1:8765`
