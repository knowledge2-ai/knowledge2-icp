# Cloudflare, K2, and Apollo Deployment Path

## Local First Slice

The current dashboard runs as a Python web app:

```bash
python3 -m icp_engine.web --host 127.0.0.1 --port 8765
```

This is intentionally lightweight so the existing Python ICP scoring engine can
be reused without duplicating the rubric in another runtime.

## Cloudflare Production Shape

This repo now includes a self-contained Worker at `deployment/cloudflare/`:

- `wrangler.toml` uploads `../../icp_engine/web_assets` as Workers static assets.
- `worker.js` serves those assets and implements seeded `/api/*` routes directly.
- `worker.js` fails closed unless `ICP_ADMIN_TOKEN` is configured, then rejects
  `/api/*` requests without `Authorization: Bearer <token>`.
- Seeded prompts, settings, ICP criteria, account lists, lead scores, prospects,
  research answers, and K2 manifests are available without a local origin.
- With `K2_API_KEY` configured, the K2 tab can upload the generated manifest to
  K2 from the Worker.
- `routes` uses a hostname-only custom domain pattern, because Cloudflare Custom
  Domains do not allow path wildcards.

Validate the shell without deploying:

```bash
wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml
```

For environment-specific dry-runs or deploys, render an ignored config rather
than editing committed placeholders:

```bash
export CLOUDFLARE_ACCOUNT_ID=<account-id>
export ICP_CLOUDFLARE_ROUTE=gtm-dev.knowledge2.ai
python3 deployment/cloudflare/preflight.py
python3 deployment/cloudflare/render_wrangler_config.py
wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml
```

Readiness probes:

```bash
curl -sS https://gtm-dev.knowledge2.ai/healthz
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  https://gtm-dev.knowledge2.ai/api/health
```

Before using a public K2 subdomain, configure `ICP_ADMIN_TOKEN` on the Worker.
Static assets can remain public, but run creation, criteria edits, K2 sync,
prospects, and research APIs should be protected because they expose GTM data
and can trigger external provider usage.

## Live Deployment Checklist

- [ ] Confirm the public hostname, for example `gtm-dev.knowledge2.ai`.
- [ ] Render `deployment/cloudflare/wrangler.generated.toml` from
  `CLOUDFLARE_ACCOUNT_ID` and `ICP_CLOUDFLARE_ROUTE`.
- [ ] Configure Cloudflare secrets: `ICP_ADMIN_TOKEN`, `K2_API_KEY`,
  `APOLLO_API_KEY`.
- [ ] Run `python3 -m unittest discover -s tests`.
- [ ] Run `make e2e-smoke`.
- [ ] Run `make cloudflare-preflight`.
- [ ] Run `wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml`.
- [ ] Check Worker `/healthz` and authenticated `/api/state`.
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

Cloudflare Worker endpoints mirror the dashboard-critical subset:

- `GET /api/state`: returns seeded criteria, prompts, settings, lists, runs,
  provider status, and latest run.
- `POST /api/search`: returns seeded/manual candidate lists.
- `POST /api/runs`: creates an isolate-local run from selected candidates.
- `GET /api/runs/{run_id}/prospects(.csv)`: returns Apollo people when
  configured and seeded persona targets as fallback.
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
