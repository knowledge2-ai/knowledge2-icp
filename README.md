# Knowledge2 ICP Qualification Engine

This repo scores company lists against the incumbent-software ICP in `icp.md`.

It is designed for Knowledge² outbound and design-partner qualification:
mature B2B/B2B2C software companies with proprietary workflow/data assets,
enough scale to feel AI pressure, and limited public AI traction.

## Quick start

```bash
python3 -m icp_engine.cli qualify --input examples/companies.csv --out out
```

Outputs:

- `out/ranked_companies.csv`
- `out/dossier.md`
- `out/cache/` with fetched public pages

## Agentic GTM dashboard

Start the local web app:

```bash
python3 -m icp_engine.web --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

The dashboard can:

- discover company candidates from a search query, committed seeds, manual seeds,
  and optional Serper/Apollo company search
- fetch public website evidence and reuse the existing ICP scoring engine
- inspect ranked leads, hard gates, evidence, strategy, and recommended personas
- inspect and export Apollo-backed prospects or strategy persona targets
- start from a committed 428-account seed universe with Volaris/Harris
  Constellation portfolio companies, named ICP examples from `icp.md`, and
  the qualified 100-company data run under `data/`
- edit the active ICP criteria markdown in local app state
- ask natural language questions over stored run evidence and metadata
- manage saved discovery sources for SERP queries, portfolio URLs, and manual
  seed lists, then scan them into candidate previews
- optionally call Apollo and GitHub providers when environment variables are configured

Set `SERPER_API_KEY` or `SERP_API_KEY` to use Google SERP discovery through
Serper. Without it, local Python falls back to DuckDuckGo HTML search and the
Cloudflare Worker falls back to Apollo company search when `APOLLO_API_KEY` is
configured, then to seeded/manual candidates.

Local app state is stored under `out/app_state` by default and is ignored by git.

For protected local API access, set an admin token before starting the server
and save the same token in the dashboard sidebar:

```bash
export ICP_ADMIN_TOKEN=$(openssl rand -hex 24)
python3 -m icp_engine.web --host 127.0.0.1 --port 8765
```

The API can run without a token only on loopback hosts by default. Public or
container binds such as `0.0.0.0` require `ICP_ADMIN_TOKEN` unless
`--allow-open-api` or `ICP_ALLOW_OPEN_API=true` is set for an isolated local
network.

Workspace durability is visible through the Setup tab and `GET
/api/workspace-state`. Local runs report file-backed state under
`out/app_state`; Cloudflare runs report whether the `ICP_STATE` KV binding is
present and which collections have persisted records.

K2 sync is dry-run by default:

```bash
python3 -m icp_engine.k2_sync --run-id <run-id> --state-dir out/app_state
```

The K2-native ICP workspace bootstrap can create the five ICP corpora,
seed/index them, and ensure the ICP agents, feeds, and PipelineSpec:

```bash
K2_API_KEY=<k2-token> K2_BASE_URL=https://api-dev.knowledge2.ai \
  python3 -m icp_engine.k2_workspace \
  --project-name "Knowledge2 ICP GTM Dev" \
  --apply-uploads --apply-indexes --apply-primitives --health-check
```

The Research tab answers from local run evidence by default. After a live K2
sync applies and stores a `corpus_id` on the run, or when `K2_RESEARCH_CORPUS_ID`
is configured, research requests use K2 generation with a `run_id` metadata
filter and fall back to local evidence search when K2 is unavailable.

The K2 tab also exposes `GET /api/k2-workspace`, a read-only status view for
the configured project, corpora, agents, feeds, PipelineSpec, and research
corpus. With `K2_API_KEY`/`K2_DEV_TOKEN` it reads live K2 state; without
credentials it falls back to the latest bootstrap summary or expected
workspace blueprint. When credentials are available, corpus rows include K2
metadata health: document count, chunk count, metadata field count, and
readiness. The same tab can call `POST /api/k2-workspace/pipeline` for
PipelineSpec `dry_run`, `apply`, `trigger`, and 30-day `backfill` actions; the
UI confirms mutating actions before dispatch.

Prospect exports are available from the dashboard Prospects tab or API:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/prospects
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/prospects.csv
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/accounts/<domain>
```

Account drilldowns also generate evidence-backed outreach drafts for each
prospect/persona. Operators can approve, reject, export, and label drafts; the
status history is stored with app state and exported for BDR review or eval
pipelines:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/outreach-drafts
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/outreach-drafts.csv
```

Saved discovery sources are available from the Sources tab or API. Source scans
reuse the configured search provider for SERP-style sources and parse manual
seed lists without calling external providers:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/sources
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Portfolio sweep","type":"serp_query","value":"vertical market software portfolio companies workflow data","schedule":"weekly"}' \
  http://127.0.0.1:8765/api/sources
```

The Sources tab also exposes a scheduled expansion loop. Cloudflare runs the
Worker `scheduled()` handler daily at `09:00 UTC`, scans enabled due sources,
persists source scans and expansion run history in KV, and keeps due-source
coverage visible in `/api/state`:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"due_only":true,"max_companies":25}' \
  http://127.0.0.1:8765/api/expansion/run
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/expansion/runs
```

Provider budget and rate-limit controls are seeded in app settings and are
reported from `/api/state` and detailed `/api/health`. Search, source scans,
runs, Apollo enrichment, research, and K2 sync actions are audited under
`provider_action.allowed` or `provider_action.denied`; denied actions return
HTTP `429` with a `provider_control` payload describing the limit.

Workspace settings can be edited from the Setup tab or saved through the API:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"default_query":"fleet workflow data limited AI positioning","max_companies":50,"provider_limits":{"daily":{"search":200},"per_run":{"max_companies":100}}}' \
  http://127.0.0.1:8765/api/settings
```

Lead workflow state is stored under `out/app_state` and survives server
restarts. API clients can mark leads as `New`, `Review`, `Qualified`,
`Rejected`, or `Exported`, bulk update lead status, save filtered lead views,
and read the audit log:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domain":"moj.io","status":"Qualified","note":"Ready for outreach"}' \
  http://127.0.0.1:8765/api/runs/<run-id>/lead-state

curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domains":["moj.io","automate.co.za"],"status":"Review","note":"BDR queue"}' \
  http://127.0.0.1:8765/api/runs/<run-id>/lead-state/bulk

curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Tier A review","filters":{"tier":"A","status":"Review"},"sort":{"field":"score","direction":"desc"},"page_size":50}' \
  http://127.0.0.1:8765/api/lead-views

curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/workflow
```

Operators can also label recommendation quality for score fit, persona fit,
and outreach usefulness. Feedback appears in account drilldowns, aggregate
state summaries, and can be exported as CSV for eval or K2 feedback pipelines:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domain":"moj.io","dimension":"score","rating":"positive","note":"Strong workflow-data fit"}' \
  http://127.0.0.1:8765/api/runs/<run-id>/quality-feedback

curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/runs/<run-id>/quality-feedback.csv
```

The Evals tab runs a deterministic quality gate over loaded data and produced
results. The first evaluator is K2-aligned but local/Worker-native: it checks
seed completeness, duplicate domains, evidence/citation coverage, gold
qualification cases, prospect role coverage, contact completeness, and outreach
readiness. K2 `EvalRun`, `GoldLabel`, feedback, quality metrics, metadata,
feeds, and agents remain the target system of record when the K2 dev project
exposes the relevant feature-gated APIs:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"<run-id>"}' \
  http://127.0.0.1:8765/api/evals/runs
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/evals/runs.csv
```

Before saving ICP criteria changes, the Criteria tab can preview threshold and
budget-range impact on the active run. The same analysis is available through
the API:

```bash
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"<run-id>","markdown":"# ICP\n\n- Tier A threshold: 80\n- Tier B threshold: 65\n"}' \
  http://127.0.0.1:8765/api/criteria/impact
```

Health checks:

```bash
curl -sS http://127.0.0.1:8765/healthz
curl -sS -H "Authorization: Bearer $ICP_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/health
```

Cloudflare Worker validation:

```bash
wrangler deploy --dry-run --config deployment/cloudflare/wrangler.toml
```

The Worker serves the dashboard assets and seeded dashboard API directly. It
uses the `ICP_STATE` KV binding to persist criteria edits, saved sources/scans,
provider usage, runtime runs, lead workflow states, saved lead views, and
quality feedback across Worker isolates. It does not require a local tunnel or a separate
`ICP_API_ORIGIN`.

For a live environment, render an ignored Wrangler config from environment
variables instead of editing committed placeholders:

```bash
export CLOUDFLARE_ACCOUNT_ID=<account-id>
export ICP_CLOUDFLARE_ROUTE=gtm-dev.knowledge2.ai
make cloudflare-dry-run
```

## Input CSV

Required:

- `company`
- `domain`

Optional:

- `category`
- `founded_year`
- `employee_count`
- `hq`
- `notes`

## Gemini-assisted scoring

Gemini is optional. Without credentials, the engine uses deterministic rules.

To enable Gemini through Vertex AI:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=global
export GEMINI_MODEL=gemini-3.5-flash
export GEMINI_THINKING_BUDGET=0
python3 -m icp_engine.cli qualify --input companies.csv --out out --use-gemini
```

The model only classifies public evidence snippets. Local scoring validates and
clamps all model output.

This repo defaults to `gemini-3.5-flash` with `GEMINI_THINKING_BUDGET=0` for
minimal thinking/low-latency classification.

## Claude qualifier (web pipeline LLM judge)

The web research pipeline can qualify each company with a Claude judge instead of
the deterministic rules. The judge reads scraped evidence, scores the five ICP
dimensions with per-dimension citations, and returns a short "what are they
building in AI" narrative. Output is confidence-gated (≥0.35) and clamped by the
local scorer, so a low-confidence or unavailable judge falls back to rules and the
run completes with a warning — a run never fails because the judge is down.

The judge reads the ICP rubric from the **versioned criteria markdown** (the same
artifact the dashboard edits), not a hardcoded prompt, so retargeting the ICP is a
criteria edit, not a code change. Each run records the `qualifier` and the
`criteria` hash it ran under.

Enable it:

```bash
pip install -e ".[claude]"
export ANTHROPIC_API_KEY=...            # do not commit
export ICP_CLAUDE_MODEL=claude-haiku-4-5-20251001   # optional; default
# then set the "qualifier" setting to "claude":
curl -sS -X POST localhost:8787/api/settings \
  -H 'content-type: application/json' \
  -d '{"qualifier":"claude"}'
```

Claude can also propose an improved ICP rubric: `POST /api/criteria/suggest`
returns a proposed markdown + rationale + diff summary. It persists nothing — the
proposal feeds the existing criteria preview/versioning flow so a human approves
the new version through the normal save path. The judge output (`source`,
per-dimension reasons, `evidence_ids` citations, `ai_narrative`) is written into
lead metadata and the K2 document manifest so the existing K2 sync/eval flow can
grade it later.

> The Cloudflare Worker is a frozen, read-only demo mirror. All qualification
> logic here is Python-only; the Worker is out of scope for this feature.

## Research-grade discovery (Perplexity)

The top of the funnel can source companies with a Perplexity Sonar research agent
instead of keyword search. Given a brief, it returns a synthesized, web-cited
company list (each with a primary domain and a one-line ICP-fit reason) mapped into
the same `DiscoveryCandidate` shape the rest of the pipeline already uses. The ICP
framing comes from the **versioned criteria markdown**, not a hardcoded prompt, so
retargeting is a criteria edit.

Provider selection is the `discovery_provider` setting:

- `auto` (default) — Perplexity when `PERPLEXITY_API_KEY` is set, otherwise the
  existing Serper → DuckDuckGo path. A set key "just works"; no key is unchanged.
- `perplexity` / `serper` / `duckduckgo` — force one engine. Perplexity still falls
  back to Serper → DuckDuckGo on an unavailable key or an upstream error, with a
  warning recorded on the run — a run never fails because Perplexity is down.

The provider that actually sourced each run is recorded at `run["discovery"]["provider"]`.
Perplexity calls are bounded by the `discovery` budget under the existing
`provider_limits` metering (the web layer returns HTTP 429 when the budget is spent),
and reduced by a **K2-aware dedup**: candidate domains already ingested in the K2
research corpus are skipped before they are researched again (no-op when K2 is
unconfigured). The Serper/DuckDuckGo fallback stays on the separate `search` budget.

The client is a hand-rolled stdlib REST client (mirroring `k2_client.py`) — there is
**no new dependency** and nothing to install.

Enable it:

```bash
export PERPLEXITY_API_KEY=...               # do not commit
export ICP_PERPLEXITY_MODEL=sonar           # optional; default
# then set the "discovery_provider" setting to "perplexity" (or "auto"):
curl -sS -X POST localhost:8787/api/settings \
  -H 'content-type: application/json' \
  -d '{"discovery_provider":"perplexity"}'
```

> The Cloudflare Worker is frozen. Research discovery is Python-only; the Worker
> mirror is out of scope.

## Personalized outreach (Claude + K2)

Each qualified lead carries a **structured buying committee** — the flat persona
list mapped into the four canonical B2B roles (economic buyer / champion / technical
evaluator / blocker), each with the Apollo titles to prospect for and the angle to
lead with. The committee is deterministic and rule-based, so it always renders even
with no LLM; it surfaces on each prospect as `committee_role`.

The per-contact **message** is where the LLM earns its place. With the
`outreach_mode` setting = `claude`, Claude drafts a role-specific email (subject,
body, CTA, angle) grounded in the scraped evidence plus best-effort **K2 account
context** — what we already know about the account from the research corpus. The
copy is generated once at run creation and cached on the lead, so reading drafts
stays cheap.

It degrades gracefully in three tiers:

- **Claude + K2** — personalized copy grounded in retrieved account context.
- **Claude only** — K2 unconfigured or a miss → personalized copy grounded in
  evidence alone (`grounded: "evidence"`).
- **Template** — `outreach_mode` is `template` (default), or Claude is unavailable
  → today's deterministic template, byte-for-byte. A run never fails on outreach.

Claude outreach reuses `ANTHROPIC_API_KEY` and is bounded by the `outreach` budget
under `provider_limits` (the web layer returns HTTP 429 when the budget is spent).
Apollo enrichment stays on its own metered `apollo_enrichment` budget.

Enable it:

```bash
export ANTHROPIC_API_KEY=...                 # do not commit; reused from the qualifier
export ICP_OUTREACH_MAX_TOKENS=700           # optional; default
# then set the "outreach_mode" setting to "claude":
curl -sS -X POST localhost:8787/api/settings \
  -H 'content-type: application/json' \
  -d '{"outreach_mode":"claude"}'
```

## Corpus mining & lookalike (K2)

The **Mining** tab searches and mines the data the funnel has *already ingested* —
not net-new internet sourcing (that is discovery, above). It answers "find companies
like my Tier-A accounts" and "show every weak-AI-posture telematics lead" over the
run/lead corpus the scheduled growth loop keeps filling.

Two operations, both hybrid:

- **Search** — metadata-filtered, faceted search. Filters are `key op value` clauses
  over the standardized metadata keys (`tier`, `ai_posture`, `vertical`, `company`,
  `total_score`, `outreach_status`, …) with ops `== != > >= < <= in contains`. Results
  come back with `tier`/`ai_posture`/`vertical` facet counts you can click to refine.
- **Lookalike** — seed a few account domains; the engine ranks other corpus companies
  by shared ICP features (vertical, AI posture, tier, score proximity) and always
  excludes the seeds themselves.

**Hybrid with local fallback.** When a corpus is configured (`K2_<NAME>_CORPUS_ID`),
mining runs as a live K2 metadata-filtered search. When K2 is unconfigured or a call
fails, it degrades to an in-memory mine over the persisted run/lead JSON — same
filters, same facets, with a warning noting the fallback. A bad filter key or op is a
`400`, not a silent local fallthrough. Pick which corpus to mine with the
`mining_corpus` setting (`auto` → the candidate corpus).

**Query profiles** (`/api/mining/profiles`) save reusable query+filter presets;
five are seeded (portfolio-expansion, ai-gap-audit, workflow-moat, budget-access,
prospect-role-tree). Mining is bounded by the `mining` budget under `provider_limits`
(HTTP 429 when spent). Export the current result set as CSV from the tab or
`POST /api/mining/search.csv`.

```bash
# Optional: point mining at live K2 corpora (keys only; do not commit values):
export K2_CANDIDATE_CORPUS_ID=...
# Unset corpora just use the local mine over persisted runs — no setup required.
```

> The Cloudflare Worker mirror is frozen — mining is Python-only.

## Validate

```bash
python3 -m unittest discover -s tests
python3 -m pip install '.[e2e]'
python3 -m playwright install chromium
make e2e-smoke
python3 -m icp_engine.cli qualify --input examples/companies.csv --out out --no-fetch
```

With deployment environment variables exported, also run:

```bash
make cloudflare-preflight
make e2e-live-auth
```

## Docs

- `docs/SCORING.md`: hard gates, posture rubric, and tiering
- `docs/GEMINI.md`: Vertex AI / Gemini service-account setup
- `docs/OPERATIONS.md`: common local runbooks
- `docs/CLOUDFLARE_K2_DEPLOYMENT.md`: Cloudflare, K2, Apollo deployment path
- `docs/designs/2026-06-13-icp-eval-pipeline.md`: K2-first eval pipeline
  design for loaded data and produced GTM results
