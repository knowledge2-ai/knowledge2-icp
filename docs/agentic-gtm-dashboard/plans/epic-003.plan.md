# Epic 003 Plan: Live K2 Sync And Cloudflare Deploy Shell

## Scope

Move beyond local manifests by adding a testable live K2 ingestion path and a Cloudflare Worker deployment shell that can host the dashboard assets and proxy API traffic. Keep secret use explicit and out of source control.

## Source Traceability

- FR-6: Consider hosting on Cloudflare.
- FR-7: Consider using Knowledge2 as backend.
- FR-9: Consider hosting under a K2 subdomain.
- FR-10: Natural-language interface with heavy metadata usage based on K2.
- NFR-13: Avoid committing secrets.

## Tasks

### T-001 Add Python K2 REST Client

Files:

- `icp_engine/k2_client.py`: implement `K2RestClient` with project/corpus list/create, document batch upload, and error handling using standard-library HTTP.
- `tests/test_k2_client.py`: cover requests with an in-process HTTP server.

Acceptance criteria:

- Uses `X-API-Key` and JSON body/response handling compatible with the K2 TypeScript SDK routes.
- Does not log or expose API key values.
- Supports dry-run-free unit tests with a fake local server.

Test command:

```bash
python3 -m unittest tests.test_k2_client
```

### T-002 Add K2 Sync Service And CLI

Files:

- `icp_engine/k2_backend.py`: convert run manifests into K2 upload documents and add `sync_manifest`.
- `icp_engine/k2_sync.py`: CLI for `--run-id`, `--manifest`, `--project-name`, `--corpus-name`, `--apply`, and dry-run defaults.
- `pyproject.toml`: add `icp-k2-sync` console script.
- `tests/test_k2_sync.py`: cover dry-run and fake apply.

Acceptance criteria:

- Dry-run returns project/corpus/document counts without network mutation.
- `--apply` requires `K2_API_KEY`.
- Upload payload uses `sourceUri`, `rawText`, and `metadata` fields.

Test command:

```bash
python3 -m unittest tests.test_k2_sync
```

### T-003 Add K2 Sync API Endpoint

Files:

- `icp_engine/web.py`: add `POST /api/runs/{run_id}/k2-sync`.
- `icp_engine/web_assets/app.js`: add K2 sync dry-run/apply controls in the K2 tab.
- `tests/test_web.py`: cover dry-run endpoint.

Acceptance criteria:

- Dry-run endpoint works without credentials.
- Apply path returns an explicit missing-secret error when `K2_API_KEY` is absent.

Test command:

```bash
python3 -m unittest tests.test_web
```

### T-004 Add Cloudflare Worker Shell

Files:

- `deployment/cloudflare/wrangler.toml`: Cloudflare Workers static assets config and secret declarations.
- `deployment/cloudflare/worker.js`: serve static assets through the `ASSETS` binding and proxy `/api/*` to `ICP_API_ORIGIN`.
- `deployment/cloudflare/README.md`: local and deploy commands, secret setup, and K2 subdomain routing notes.
- `tests/test_cloudflare_config.py`: parse the TOML enough to verify required keys and no committed secrets.

Acceptance criteria:

- Worker config follows current Cloudflare static asset configuration (`assets.directory`).
- Required secrets are declared by name only.
- No Cloudflare/K2/Apollo token values appear in config.

Test command:

```bash
python3 -m unittest tests.test_cloudflare_config
```

### T-005 Documentation And Verification

Files:

- `docs/CLOUDFLARE_K2_DEPLOYMENT.md`: document live K2 sync and Cloudflare worker shell.
- `docs/OPERATIONS.md`: document CLI/API usage.
- `docs/agentic-gtm-dashboard/state.md`: update Epic 3 status.

Acceptance criteria:

- `python3 -m py_compile icp_engine/*.py` passes.
- `python3 -m unittest discover -s tests` passes.
- Local server exposes the K2 sync endpoint.

Test command:

```bash
python3 -m py_compile icp_engine/*.py
python3 -m unittest discover -s tests
```
