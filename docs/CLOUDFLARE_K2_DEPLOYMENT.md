# Cloudflare, K2, and Apollo Deployment Path

## Local First Slice

The current dashboard runs as a Python web app:

```bash
python3 -m icp_engine.web --host 127.0.0.1 --port 8765
```

This is intentionally lightweight so the existing Python ICP scoring engine can
be reused without duplicating the rubric in another runtime.

## Cloudflare Production Shape

`gtm-dev.knowledge2.ai` runs the same Python engine as local, deployed to a
private **Cloud Run** service and fronted by a thin **Cloudflare Worker proxy**:

- `deployment/cloudrun/` builds and deploys the engine (`Dockerfile`,
  `cloudbuild.yaml`, `deploy.sh`). The service is private — the org policy
  blocks `allUsers` — so it is never reachable directly from the internet.
- `deployment/cloudflare-proxy/worker.js` mints a Google ID token (RS256 JWT,
  audience = the Cloud Run URL) from a service-account key held in Worker
  secrets, and forwards every request to Cloud Run with that token.
- The route is bound hostname-only (`gtm-dev.knowledge2.ai/*`), because
  Cloudflare Custom Domains do not allow path wildcards.
- The engine runs with `ICP_PUBLIC_READ_ONLY=true` on Cloud Run: the read-only
  demo endpoints (`/api/health`, `/api/runs/{id}/prospects[.csv]`) are public
  and every write returns 401.

Validate the proxy shell without deploying:

```bash
cd deployment/cloudflare-proxy && wrangler deploy --dry-run
```

Deploy / cutover (one-time; see `deployment/cloudflare-proxy/README.md`):

```bash
deployment/cloudrun/deploy.sh        # PROJECT=... SERVICE=gtm-demo AUTH=readonly
bash deployment/cloudflare-proxy/cutover.sh
```

Readiness probes:

```bash
curl -sS https://gtm-dev.knowledge2.ai/api/health
curl -sS https://gtm-dev.knowledge2.ai/api/runs/run-seeded-icp/prospects
```

The proxy holds the Cloud Run invoker credential, so public callers never need a
token for the read-only endpoints. Writes are refused by the engine itself
(`ICP_PUBLIC_READ_ONLY`), not by an edge token.

## Live Deployment Checklist

- [ ] Confirm the public hostname, for example `gtm-dev.knowledge2.ai`.
- [ ] Deploy the engine to Cloud Run: `deployment/cloudrun/deploy.sh`
  (`AUTH=readonly` for the public demo).
- [ ] Set the proxy's `CLOUD_RUN_URL` in
  `deployment/cloudflare-proxy/wrangler.toml`.
- [ ] Run `python3 -m unittest discover -s tests`.
- [ ] Run `make e2e-smoke`.
- [ ] Run `cd deployment/cloudflare-proxy && wrangler deploy --dry-run`.
- [ ] Run `bash deployment/cloudflare-proxy/cutover.sh` (deploys the proxy and
  sets the `GCP_SA_*` secrets).
- [ ] Check `https://gtm-dev.knowledge2.ai/api/health` (`version`,
  `public_read_only: true`) and that a write returns 401.
- [ ] Run K2 sync dry-run from the K2 tab before any apply upload.

## Knowledge2 Backend Contract

Every evidence item is exported with stable metadata keys:

- `run_id`
- `query`
- `company`
- `domain`
- `tier`
- `total_score`
- `source_type`
- `source_url`
- `evidence_id`

That metadata is sufficient to upload documents to a K2 corpus, build indexes,
and later call K2 search/generate for the natural-language research panel. The
first slice includes `icp_engine.k2_backend.K2Backend` to build this manifest and
report provider readiness without committing API keys.

Local API endpoints:

- `GET /api/runs/{run_id}/k2-manifest`: returns a manifest preview without
  writing files.
- `POST /api/runs/{run_id}/k2-export`: writes the manifest to local app state
  and returns `export_path`.
- `POST /api/research`: uses local stored evidence by default, or K2 generation
  when the run has an uploaded `corpus_id` or `K2_RESEARCH_CORPUS_ID` is set.

The engine (local and on Cloud Run behind the proxy) serves the dashboard-critical subset:

- `GET /api/state`: returns seeded criteria, prompts, settings, lists, runs,
  provider status, and latest run.
- `GET /api/workspace-state`: reports `ICP_STATE` KV durability and persisted
  collection counts for runs, settings, sources, workflow state, evals, and
  feedback.
- `POST /api/search`: returns seeded/manual candidate lists.
- `POST /api/runs`: creates an isolate-local run from selected candidates.
- `GET /api/runs/{run_id}/prospects(.csv)`: returns Apollo people when
  configured and seeded persona targets as fallback.
- `GET /api/k2-workspace`: reports the configured K2 project, corpora, agents,
  feeds, PipelineSpec, research corpus, and missing-resource warnings.
- `POST /api/k2-workspace/pipeline`: runs the configured PipelineSpec
  `dry_run`, `apply`, `trigger`, or 30-day `backfill` action. The dashboard UI
  confirms mutating actions before dispatch.
- `GET /api/runs/{run_id}/k2-manifest`: returns K2-ready metadata documents.
- `POST /api/runs/{run_id}/k2-sync`: dry-runs or uploads to K2 when
  `K2_API_KEY` is configured and `apply=true`.

The manifest contains one `account_summary` document per lead plus one document
per evidence item. Evidence documents include metadata such as `source_type`,
`page_category`, `signal_tags`, `persona_titles`, `tier`, `total_score`,
`ai_posture`, `source_url`, and `criteria_hash`. That is the expected metadata
filter surface for K2-backed natural-language research.

Live upload path:

```bash
python3 -m icp_engine.k2_sync --run-id {run_id} --state-dir out/app_state
python3 -m icp_engine.k2_sync --run-id {run_id} --state-dir out/app_state --apply
```

The first command is a dry-run. The second command requires `K2_API_KEY` and
creates or reuses a K2 project/corpus before uploading `sourceUri`, `rawText`,
and `metadata` documents through K2's batch document route.

K2-backed research uses the same retrieval posture as the referenced demos:
hybrid search with metadata-sparse enabled, source text/scores/provenance
returned, and a `run_id` metadata filter so answers are grounded in the selected
ICP run rather than a broad corpus.

## Apollo Contract

Apollo is optional and configured with `APOLLO_API_KEY`. The adapter is designed
around the public Apollo endpoint shapes:

- Organization Search: `POST /api/v1/mixed_companies/search`
- People Search: `POST /api/v1/mixed_people/api_search`

The app uses Apollo for enrichment and target prospect discovery. If Apollo is
not configured, the dashboard still recommends personas from scoring and
vertical rules.

Prospect data is exposed through:

- `GET /api/runs/{run_id}/prospects`: ranked JSON rows with company, domain,
  title, persona, source, LinkedIn URL, email when available, and outreach angle.
- `GET /api/runs/{run_id}/prospects.csv`: stable CSV export for outbound tools.

K2 manifests also include prospect/persona documents with `source_type=prospect`,
`page_category=persona`, `persona_titles`, and `outreach_angle` metadata so
natural-language research can retrieve the recommended outreach target context
alongside account evidence.

## LinkedIn Handling

Do not implement authenticated LinkedIn scraping in the web app. Store public
LinkedIn URLs discovered through search or Apollo metadata, and let Apollo or a
compliant enrichment provider resolve people and company records.

## Secret Hygiene

Do not commit real tokens. Configure them locally through `.env` or in
Cloudflare using worker/page secrets. If tokens were shared in chat, rotate them
before production deployment.
