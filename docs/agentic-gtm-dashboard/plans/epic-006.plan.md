# Epic 006 Plan: Deployment Readiness And Completion Audit

## Scope

Add deploy-readiness probes and a requirement-level completion audit so the local app, Cloudflare shell, and K2/Apollo integration path have concrete operational evidence. This epic does not perform live Cloudflare/K2 mutation; live deployment still requires operator confirmation of subdomain, API origin, and production secrets.

## Source Traceability

- FR-1: Provide a web dashboard as the primary interface.
- FR-11: Include a Knowledge2 backend integration path for storing/querying enriched evidence with metadata.
- FR-12: Include a Cloudflare deployment plan and configuration surface suitable for a K2 subdomain.
- FR-13: Avoid committing secrets.
- NFR-2: External enrichers must be optional and degrade gracefully.
- NFR-6: Tests must cover provider fallbacks and web API behavior.

## Tasks

### T-001 Add Local Health And Readiness Endpoints

Files:

- `icp_engine/web.py`: add public `GET/HEAD /healthz` liveness and authenticated `GET /api/health` readiness when `ICP_ADMIN_TOKEN` is configured.
- `tests/test_web.py`: cover public liveness, protected readiness, and authenticated readiness.

Acceptance criteria:

- `/healthz` remains public so Cloudflare and local process monitors can probe the origin without an admin token.
- `/api/health` returns provider status and auth state but follows the same API auth boundary as other `/api/*` routes.
- No secrets are returned in health payloads.

Test command:

```bash
python3 -m unittest tests.test_web
```

### T-002 Add Cloudflare Edge Health Probe

Files:

- `deployment/cloudflare/worker.js`: return public edge health JSON at `/healthz` and keep `/api/*` auth behavior unchanged.
- `tests/test_cloudflare_config.py`: verify the worker declares a `/healthz` route and does not commit secret-shaped values.

Acceptance criteria:

- `GET /healthz` on the Worker can confirm edge asset/proxy configuration without hitting protected APIs.
- The payload does not include secret values.

Test command:

```bash
python3 -m unittest tests.test_cloudflare_config
wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml
```

### T-003 Document Deploy Readiness And Completion Audit

Files:

- `README.md`: add health/readiness probe commands.
- `docs/OPERATIONS.md`: add local and protected readiness checks.
- `docs/CLOUDFLARE_K2_DEPLOYMENT.md`: add deploy-readiness checklist for subdomain, API origin, secrets, health probes, and dry-runs.
- `docs/agentic-gtm-dashboard/completion-audit.md`: map each user requirement to current evidence and remaining gaps.
- `docs/agentic-gtm-dashboard/state.md`: update Epic 6 progress.
- `docs/agentic-gtm-dashboard/plans/_iteration-state.md`: update Epic 6 status.

Acceptance criteria:

- The audit distinguishes completed evidence from remaining operator decisions.
- The deploy checklist is concrete enough to execute after user confirmation.

Test command:

```bash
python3 -m py_compile icp_engine/*.py
python3 -m unittest discover -s tests
node --check icp_engine/web_assets/app.js
```
