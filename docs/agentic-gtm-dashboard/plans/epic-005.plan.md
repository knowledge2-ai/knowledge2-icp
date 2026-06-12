# Epic 005 Plan: Production Hardening And Deployment Guardrails

## Scope

Add the first production safety boundary around the dashboard API and Cloudflare proxy while preserving zero-config local development. This epic focuses on admin/API bearer-token protection, secret workflow documentation, and validation. Browser E2E remains deferred because the repo currently has no Playwright/Cypress/package infrastructure.

## Source Traceability

- FR-6: Provide an admin UI to view and edit ICP criteria markdown/prompt.
- FR-11: Include a Knowledge2 backend integration path for storing/querying enriched evidence with metadata.
- FR-12: Include a Cloudflare deployment plan and configuration surface suitable for a K2 subdomain.
- FR-13: Avoid committing secrets; all API keys and tokens must be provided via environment variables or Cloudflare secrets.
- NFR-4: The UI must be dense, operational, and polished for repeated GTM workflow use.
- Design Security Consideration: Production requires auth before exposing criteria editing.

## Tasks

### T-001 Add Optional API Bearer Authentication

Files:

- `icp_engine/web.py`: add `ICP_ADMIN_TOKEN` / `--admin-token` support, protect `/api/*` when configured, and return JSON `401` with `WWW-Authenticate`.
- `tests/test_web.py`: cover open local mode, missing token, bad token, and valid token.

Acceptance criteria:

- Local development remains open when no admin token is configured.
- All `/api/*` routes require `Authorization: Bearer <token>` when a token exists.
- Static assets remain readable without a token.
- Token comparison does not use naive equality.

Test command:

```bash
python3 -m unittest tests.test_web
```

### T-002 Add Dashboard Token Handling

Files:

- `icp_engine/web_assets/index.html`: add a compact admin token control in the sidebar.
- `icp_engine/web_assets/app.js`: store the token in `localStorage`, attach it to API requests, and surface auth errors.
- `icp_engine/web_assets/styles.css`: style the token control without disrupting the dense dashboard layout.

Acceptance criteria:

- Operators can save and clear an admin token from the dashboard.
- API calls automatically include the bearer token when saved.
- The UI still works unchanged in open local mode.

Test command:

```bash
node --check icp_engine/web_assets/app.js
```

### T-003 Add Cloudflare Edge Auth Guard

Files:

- `deployment/cloudflare/worker.js`: require bearer auth for `/api/*` when `ICP_ADMIN_TOKEN` is present in Worker secrets and avoid forwarding invalid requests to origin.
- `deployment/cloudflare/wrangler.toml`: declare `ICP_ADMIN_TOKEN` as a required secret name only.
- `tests/test_cloudflare_config.py`: verify the secret name is declared and no secret-shaped values are committed.

Acceptance criteria:

- Worker returns `401` for missing or invalid API tokens when configured.
- Worker still supports open proxy mode when the secret is absent for local preview.
- Real token values are not present in source.

Test command:

```bash
python3 -m unittest tests.test_cloudflare_config
wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml
```

### T-004 Documentation And E2E Phase Decision

Files:

- `.env.example`: add `ICP_ADMIN_TOKEN=`.
- `README.md`: document local admin-token mode and dashboard token control.
- `docs/OPERATIONS.md`: document API calls with bearer auth.
- `deployment/cloudflare/README.md`: document `ICP_ADMIN_TOKEN` secret setup.
- `docs/CLOUDFLARE_K2_DEPLOYMENT.md`: document production API auth boundary.
- `docs/agentic-gtm-dashboard/state.md`: record Epic 5 status and E2E skip reason.
- `docs/agentic-gtm-dashboard/plans/_iteration-state.md`: mark Epic 5 progress and backlog.

Acceptance criteria:

- Deployment docs explain that API/admin access must be protected before a public K2 subdomain is used.
- E2E status is explicit: skipped for now because no E2E infrastructure exists.

Test command:

```bash
python3 -m py_compile icp_engine/*.py
python3 -m unittest discover -s tests
node --check icp_engine/web_assets/app.js
```
