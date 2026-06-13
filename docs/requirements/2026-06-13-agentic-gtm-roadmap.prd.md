# PRD: Agentic GTM Platform End-to-End Analysis And Feature Roadmap

<!--
METADATA:
prd_id: 2026-06-13-agentic-gtm-roadmap
date: 2026-06-13
status: Draft
product_area: Knowledge2 ICP / Agentic GTM Dashboard
target_release: TBD
total_functional_reqs: 17
total_nonfunctional_reqs: 10
total_user_stories: 10
-->

**Date:** 2026-06-13  
**Author:** AI Requirements Analyst  
**Status:** Draft  
**Product area:** Knowledge2 ICP / Agentic GTM Dashboard  
**Target release:** TBD  
**Stakeholders:** GTM operators, sales/research users, platform operators, Knowledge2/K2 integration owners

## 1. Executive Summary

The software has evolved from a deterministic ICP scoring CLI into an operator-facing Agentic GTM dashboard. It now supports candidate discovery, public evidence collection, ICP scoring, strategy/persona generation, prospect export, criteria editing with lint/version controls, K2 manifest export/sync, and Cloudflare Worker deployment. The live dev route currently returns a seeded 428-account universe, with K2 and Apollo configured and SERP discovery not configured on the Worker.

The product is useful today as a dev/demo control plane and research console. The largest remaining opportunity is to turn it from a static/run-based dashboard into a durable GTM workflow system: persistent lead pipelines, deeper prospect/contact enrichment, workflow states, operator collaboration, stronger search/scraping orchestration, and production controls around cost, security, auditability, and quality gates.

The highest-value next features are: persistent lead workspaces, account/prospect drill-down pages, richer discovery with SERP + portfolio source ingestion, contact verification/outreach workflow, a K2-native ICP expansion pipeline built from Agents/Feeds/Pipelines/Metadata/Quality primitives, production auth/rate limiting, and expanded E2E/visual coverage.

## 2. Current Product Assessment

### 2.1 User-Facing Capabilities

| Area | Current behavior | Evidence |
| --- | --- | --- |
| Discovery | Operators can search, use committed seeds, enter manual seeds, and optionally use Serper/Apollo company discovery. | `README.md:31-48`, `icp_engine/research.py:42-49`, `/api/search` in `icp_engine/web.py:141-166` |
| Scoring | Runs load active criteria, build a criteria profile, fetch evidence, score each candidate, create strategy, and persist a run. | `icp_engine/research.py:63-132`, `docs/SCORING.md` |
| Leads | Dashboard renders lead rows, tier/score, strategy, evidence, hard gates, active criteria, source metadata, and review flags. | `icp_engine/web_assets/index.html`, `icp_engine/web_assets/app.js` |
| Prospects | Prospects are built from Apollo people when present; otherwise strategy persona targets are exported as fallback. | `icp_engine/prospects.py`, `README.md:76-83` |
| Criteria editing | Active criteria markdown can be edited, linted, formatted, versioned, restored, and saved. | `/api/criteria*` in `icp_engine/web.py:120-139`, `icp_engine/criteria_editor.py` |
| Research | Research answers use local evidence by default and can use K2 generation when a synced corpus or K2 corpus env is available. | `README.md:71-74`, `icp_engine/research.py:134-145` |
| K2 export/sync | Run manifests can be previewed, exported, dry-run synced, or applied to K2 with credentials. | `icp_engine/web.py:194-218`, `docs/CLOUDFLARE_K2_DEPLOYMENT.md` |
| Cloudflare deploy | Worker serves assets and seeded API routes, with direct Cloudflare deployment path. | `deployment/cloudflare/worker.js`, `docs/CLOUDFLARE_K2_DEPLOYMENT.md` |
| E2E validation | A Playwright smoke runner exercises the local dashboard, prospects, research, K2 preview, setup, and criteria editor. | `tests/e2e/e2e-test-plan.md:1-44`, `tests/e2e/run_dashboard_smoke.py` |

### 2.2 Live Dev Snapshot

Observed from `https://gtm-dev.knowledge2.ai/api/state` during this analysis:

| Signal | Value |
| --- | --- |
| Active run | `run-seeded-icp` |
| Live lead count | 428 |
| Seed account count | 428 |
| Prompt count | 4 |
| Priority vertical count | 12 |
| Criteria versions | 1 |
| Apollo | configured |
| K2 | configured against `https://api-dev.knowledge2.ai` |
| Worker search provider | `apollo-company-search` |
| SERP | not configured |

### 2.3 Strengths

- Strong seeded demo state: the app is useful immediately without running a live crawl.
- Clear GTM workflow spine: Discover -> Leads -> Prospects -> Research -> K2.
- Criteria are operational, not decorative; active markdown affects scoring metadata.
- The prospect tree and export path support outbound handoff.
- K2 manifests preserve metadata needed for retrieval and cited research.
- Local and Cloudflare paths both have tests and deployment preflight.
- Security posture is reasonable for dev/admin use: secrets are environment-backed, static assets are public, and mutating K2 sync has explicit apply flow.

## 3. Key Gaps

| Gap ID | Area | Current state | Gap | Severity |
| --- | --- | --- | --- | --- |
| G-1 | Durable workflow | Runs are stored locally or in Worker runtime/seeded state. | No durable multi-run workspace, lead state, review queue, ownership, or persisted Cloudflare criteria history. | High |
| G-2 | Discovery depth | Search exists, but live Worker SERP is not configured and source ingestion is query-centric. | No managed source library for portfolio pages, directories, saved searches, scheduled crawls, or source coverage scoring. | High |
| G-3 | Contact quality | Apollo people can be fetched, fallback personas exist. | No contact verification, confidence, deduplication across runs, role hierarchy tuning, or outreach readiness status. | High |
| G-4 | Account drill-down | Clicking a lead shifts into prospects; details are in a panel. | No durable account page with timeline, source graph, prospects tree, research notes, and action history. | High |
| G-5 | Outreach execution | Exports CSV/JSON and generates angles. | No sequenced outreach drafts, personalization variants, CRM/export integrations, or reply/status tracking. | High |
| G-6 | K2 research memory | K2 sync/research path exists. | No always-on corpus lifecycle, incremental update, document deletion/replacement, or answer quality evaluation loop. | Medium |
| G-7 | Production controls | Auth exists; security review flags low-risk gaps. | No first-class user accounts, roles, short-lived sessions, audit trail, rate limiting, or provider budget guardrails. | High |
| G-8 | UI scale | Dense tables render hundreds of leads. | No pagination, sorting, saved filters, bulk selection, custom views, or queue triage ergonomics. | Medium |
| G-9 | Test coverage | E2E smoke validates happy path. | No auth-on, live provider mocked failure, mobile/visual regression, or destructive-action guard E2E suite. | Medium |
| G-10 | Measurement | Score and tier exist per lead. | No conversion outcomes, precision/recall feedback, model/rules evaluation, or recommendation quality analytics. | Medium |
| G-11 | K2 primitives | K2 export/sync creates documents for a run and can answer questions over a corpus. | The app does not create or operate K2 Agents, Feeds, Pipelines, Subscriptions, query profiles, or feedback loops. | High |
| G-12 | Ongoing ICP growth | Discovery is run/search driven and seeded from 428 accounts. | No scheduled or reactive K2 mechanism keeps source corpora, candidate corpora, qualification outputs, and prospect records growing over time. | High |
| G-13 | Criteria refinement | Criteria markdown affects scoring and can be versioned. | Search criteria are not learned from accepted/rejected accounts, metadata distributions, feed outcomes, or K2 quality signals. | High |

## 4. Stakeholder Map

| Stakeholder | Role | Primary concern | Impact |
| --- | --- | --- | --- |
| GTM operator | Runs searches, triages leads, exports prospects | Fast account discovery, high signal, low manual cleanup | High |
| Sales/research user | Reviews company evidence and prospects | Trustworthy evidence, clear contact path, personalized messaging | High |
| Platform operator | Deploys and monitors Cloudflare/K2 path | Security, reliability, secrets, provider costs | High |
| ICP owner | Edits criteria and validates scoring | Versioned criteria, explainability, scoring consistency | Medium |
| Knowledge2/K2 owner | Owns ingestion/retrieval path | Metadata quality, corpus lifecycle, cited answers | Medium |

## 5. User Stories

| ID | As a... | I want to... | So that... | Priority | Reqs |
| --- | --- | --- | --- | --- | --- |
| US-1 | GTM operator | save and resume lead workspaces across sessions | I can run ongoing account research without losing state | Must | FR-1, FR-2 |
| US-2 | GTM operator | ingest source lists and scheduled searches | the system continuously expands the target universe | Must | FR-3 |
| US-3 | Sales/research user | open a company and see prospects in a role tree | I can understand who to contact and why | Must | FR-4 |
| US-4 | Sales/research user | generate verified outreach drafts per prospect | I can move from research to outbound faster | Should | FR-5 |
| US-5 | ICP owner | compare criteria versions against scored runs | I can see how criteria changes affect lead ranking | Should | FR-6 |
| US-6 | Platform operator | enforce provider budgets and audit activity | the deployed system cannot silently spend or mutate at scale | Must | FR-7, NFR-4 |
| US-7 | K2 owner | maintain a durable research corpus per workspace | answers remain grounded in the latest accepted evidence | Should | FR-8 |
| US-8 | Operator/admin | validate the full workflow before each deploy | releases do not regress core GTM flows | Must | FR-12, NFR-7 |
| US-9 | GTM operator | let K2 continuously discover and qualify new ICP accounts | the lead universe expands without manually rerunning one-off searches | Must | FR-13, FR-14, FR-15 |
| US-10 | ICP owner | refine search criteria from accepted, rejected, and converted accounts | future discovery focuses on the best-fit K2 targets | Should | FR-16, FR-17 |

## 6. Proposed Functional Requirements

| ID | Requirement | Priority | Acceptance criteria |
| --- | --- | --- | --- |
| FR-1 | Introduce durable GTM workspaces with persistent runs, lead state, saved filters, and operator notes. | Must | Workspaces persist across deploy/restart; operators can mark leads as New/Review/Qualified/Rejected/Exported; state is visible in Leads and Runs. |
| FR-2 | Add bulk lead triage and queue controls. | Must | Operators can sort, paginate, filter by score/tier/source/status, select multiple leads, bulk reject/export, and save named views. |
| FR-3 | Add managed source ingestion for portfolio pages, directories, CSV uploads, and saved SERP queries. | Must | Sources can be added, scanned, deduped, scheduled, and reviewed with source-level coverage/warnings. |
| FR-4 | Add account drill-down pages with prospect tree, evidence graph, source timeline, strategy, criteria snapshot, and research notes. | Must | Clicking a company opens a stable account view; prospects are grouped by role/persona; all evidence and source refs are inspectable. |
| FR-5 | Add outreach workspace with message generation, personalization variables, sequence variants, CSV/CRM export, and approval status. | Should | Each prospect can have draft subject/body/CTA; drafts cite evidence; operators can approve/export selected drafts. |
| FR-6 | Add criteria impact analysis. | Should | Operators can compare two criteria versions and see expected threshold/profile differences plus affected run/lead tiers. |
| FR-7 | Add provider budget, rate limit, and audit controls. | Must | Search/run/K2/apply actions are logged; rate limits are enforced; provider calls have per-run and daily budgets; denied actions have visible reasons. |
| FR-8 | Add K2 corpus lifecycle management. | Should | Operators can see corpus sync status, last upload, document count, stale documents, re-sync action, and retrieval health checks. |
| FR-9 | Add research task queue and background execution status. | Should | Long crawls/enrichment runs move to queued/running/completed/failed states; UI shows progress and partial results. |
| FR-10 | Add quality feedback loop for lead/prospect recommendations. | Should | Operators can mark score/persona/outreach quality; aggregate feedback appears in reports and can be exported. |
| FR-11 | Add admin settings UI for prompts, settings, provider config status, and list management. | Could | Setup tab can edit safe settings/lists/prompts with validation and version history. |
| FR-12 | Expand E2E/visual validation suite. | Must | CI can run local smoke, auth-on smoke, mobile screenshots, provider-failure cases, and criteria editor/versioning flows. |
| FR-13 | Add a K2-native ICP Expansion PipelineSpec. | Must | A pipeline spec can describe source corpora, candidate/evidence/prospect corpora, extraction agents, qualification agents, feeds, and subscriptions; dry-run/apply/trigger/backfill state is visible in the app. |
| FR-14 | Add K2 Agent definitions for company extraction, qualification, prospect/persona extraction, evidence-gap detection, criteria refinement, and outreach draft support. | Must | Agents use declared schemas for structured fields and preserve prompt/model/version metadata; active/draft states are visible before scheduled execution. |
| FR-15 | Add scheduled and reactive K2 Feeds for ongoing ICP expansion. | Must | Persistent feeds can run on interval or UTC cron, reactive feeds can fire on source-corpus changes, backfills can resweep historical source events, and results are written into target corpora with lineage metadata. |
| FR-16 | Use K2 metadata discovery, query profiles, filters, and feedback to tune search criteria. | Should | The app can discover metadata keys/top values, save example ICP queries and dataset hints, search with metadata filters, and record positive/negative feedback for accepted/rejected leads. |
| FR-17 | Add source coverage and expansion observability. | Should | Operators can see source coverage by source group/vertical/status, feed run history, new-candidate counts, dropped/failed delivery counts, and stale/missing evidence gaps. |

## 7. Non-Functional Requirements

| ID | Category | Requirement | Current baseline | Target | Priority |
| --- | --- | --- | --- | --- | --- |
| NFR-1 | Durability | Production state must survive Worker restarts and deploys. | Worker runtime history is ephemeral; local state is file-based. | Durable Cloudflare/K2-backed workspace storage. | Must |
| NFR-2 | Security | Production API access must use short-lived sessions or equivalent strong auth. | Bearer token can be stored in browser localStorage. | Role-aware sessions, audit trail, no long-lived browser token by default. | Must |
| NFR-3 | Cost control | Provider usage must be bounded and observable. | No API rate limiting or budget controls in app. | Per-user/per-workspace limits, visible budget, blocked-over-budget actions. | Must |
| NFR-4 | Explainability | Scores and messages must be traceable to criteria and evidence. | Score metadata, evidence, citations exist. | Every score/outreach draft exposes top evidence and criteria rules. | Must |
| NFR-5 | Performance | Hundreds to thousands of leads should remain usable. | 428 rows render in one table. | Pagination/virtualization; common filters under 300 ms locally. | Should |
| NFR-6 | Reliability | Long discovery/enrichment jobs should be recoverable. | Runs execute synchronously in local API path. | Background jobs with resumable state and error recovery. | Should |
| NFR-7 | Testability | Critical GTM paths must be validated before deploy. | 6-item E2E smoke plan. | CI matrix for auth, mobile, live-worker dry run, and visual snapshots. | Must |
| NFR-8 | Compliance | Contact data handling must remain compliant. | Apollo used as optional source; no authenticated LinkedIn scraping. | Export/audit rules and documented source policy for person data. | Must |
| NFR-9 | Lineage | Every K2-generated candidate, evidence item, qualification result, and prospect record must be traceable to source input, criteria version, agent version, feed run, and pipeline run where available. | Current K2 export metadata includes run/company/source fields but not K2 agent/feed/pipeline lineage. | K2 document metadata and envelopes carry `run_id`, `criteria_hash`, `agent_id`, `feed_id`, `feed_run_at`, `pipeline_run_id`, `source_url`, and source-corpus provenance. | Must |
| NFR-10 | Preview-feature safety | K2 preview primitives must fail visibly when feature flags, quotas, indexes, or schedules are unavailable. | Current ICP app treats K2 as optional upload/research backend. | The UI exposes K2 feature flag readiness, quota failures, index-not-ready states, backfill conflicts, and feed/agent draft vs active status. | Must |

## 8. Recommended Feature Roadmap

### Phase 1: Make It A Durable Operator Tool

1. Persistent workspaces and lead statuses.
2. Lead table sorting, pagination, saved filters, and bulk actions.
3. Account drill-down page with prospect tree and evidence timeline.
4. Audit log for criteria edits, run creation, exports, and K2 apply.
5. Expanded E2E for auth-on, Criteria, Prospects, K2 dry-run, and mobile.

### Phase 2: Make Discovery Systematic

1. Source ingestion manager for CSV, portfolio pages, directories, and saved SERP queries.
2. Scheduled searches/crawls with run queue.
3. Source coverage scoring and duplicate resolution.
4. SERP provider configuration on live Worker, with budget/limits.
5. Discovery results review queue before scoring.
6. K2 source corpora for portfolio/source pages and SERP/Apollo discovery results.
7. K2 persistent feeds that extract and append normalized candidate records into a candidate corpus.

### Phase 3: Make Prospects Actionable

1. Contact verification/confidence and enrichment provenance.
2. Role hierarchy tuning per ICP/persona.
3. Outreach draft generation with evidence-backed personalization.
4. Export packages for Apollo/CRM/CSV with status tracking.
5. Quality feedback on prospect fit and message usefulness.

### Phase 4: Make K2 The ICP Expansion Engine

1. Workspace-level K2 corpus lifecycle and health panel.
2. Incremental sync, stale-document detection, and reindex status.
3. K2-backed account Q&A with source-grounded answer cards.
4. Research notes and answer pinning per account/prospect.
5. Evaluation set for answer quality and citation coverage.
6. K2 Agent definitions for extraction, qualification, evidence-gap detection, prospect/persona extraction, and criteria refinement.
7. K2 PipelineSpec authoring/apply/trigger/backfill controls for the ICP growth graph.
8. K2 metadata discovery and query-profile tuning for best-fit search criteria.
9. K2 feedback and quality metrics for accepted/rejected leads and search filter performance.

### Phase 5: Production Hardening

1. Strong auth/session model and role-based permissions.
2. Cloudflare/API rate limiting and provider spend guardrails.
3. CI deploy gate with unit, E2E, Worker dry-run, and secret scan.
4. Visual regression for desktop/mobile core tabs.
5. Observability dashboard for run duration, provider failures, and sync outcomes.

## 9. Feature Priority Matrix

| Rank | Feature | Why now | Effort | Risk |
| --- | --- | --- | --- | --- |
| 1 | Durable workspaces + lead statuses | Without durable workflow, the app remains a demo/control panel. | M | Medium |
| 2 | Account drill-down + prospect tree | Directly addresses the operator need to click a company and inspect prospects/roles. | M | Low |
| 3 | Discovery source manager + SERP configuration | Expands from seeded demo to continuous account discovery. | M | Medium |
| 4 | Contact verification + outreach drafts | Converts research output into outbound-ready action. | L | Medium |
| 5 | Provider budgets + audit logs | Needed before broad use with paid APIs and K2 mutation paths. | M | Low |
| 6 | K2 corpus lifecycle | Makes K2 research reliable instead of optional/manual. | M | Medium |
| 7 | Expanded E2E/visual suite | Reduces regression risk as UI/workflow complexity grows. | S | Low |
| 8 | Criteria impact analysis | Helps ICP owner trust edits before reruns. | S | Low |
| 9 | K2-native ICP expansion pipeline | Turns static discovery into scheduled/reactive growth with lineage and feedback. | L | Medium |
| 10 | K2 metadata/query-profile tuning | Makes search criteria improve from actual fit signals instead of manual prompt edits only. | M | Medium |

## 10. Open Questions

| ID | Question | Why it matters |
| --- | --- | --- |
| Q-1 | Should the production target remain Cloudflare Worker-only, or should durable workflow state move to GKE/K2-backed services? | Determines storage/job architecture and runtime limits. |
| Q-2 | Which CRM/outbound system is the first export target? | Shapes outreach package format and required fields. |
| Q-3 | Should all `/api/*` routes be protected in dev Cloudflare, or remain public read-only with only apply sync protected? | Defines launch security posture. |
| Q-4 | What is the expected daily discovery volume: hundreds, thousands, or tens of thousands of companies? | Determines pagination, queue, budget, and storage requirements. |
| Q-5 | Is K2 intended to be the system of record for run evidence, or only a retrieval/index layer? | Determines corpus lifecycle and deletion/update semantics. |
| Q-6 | What qualifies a prospect as "outreach-ready": email present, LinkedIn present, title match, or verified contact? | Drives prospect status and export rules. |
| Q-7 | Should the first K2-native implementation target one workspace/project only, or support multiple GTM workspaces from day one? | Determines corpus naming, pipeline spec reuse, quota planning, and UI scope. |
| Q-8 | Which feedback signal is authoritative for criteria refinement: operator accepted/rejected, Apollo export, meeting booked, reply, or opportunity created? | Determines quality labels and query-profile optimization targets. |

## 11. Immediate Next Implementation Candidates

1. **K2-native ICP Expansion PipelineSpec:** Define the corpora, agents, feeds, subscriptions, metadata, and schedules needed to grow the ICP continuously.
2. **Account drill-down page:** Highest user-visible value; fits current frontend/API model.
3. **Persistent lead status and saved filters:** Turns the dashboard into a daily workflow surface.
4. **Cloudflare durable criteria/workspace storage:** Fixes the current Worker runtime-state limitation.
5. **Provider budget/audit log:** Hardens production use before broader operation.
6. **SERP setup and source ingestion UI:** Expands discovery beyond seeded/Apollo fallback.

## 12. K2 Primitive Research Findings

This section reflects a targeted read of `/Users/antonmishel/k2/k2_mvp`, excluding `_archive`.

| Primitive | Current K2 status | Evidence in K2 | ICP product implication |
| --- | --- | --- | --- |
| Corpus, Document, Chunk | Stable core primitives for ingestion, indexing, retrieval, and metadata. | `docs/architecture/concepts/data-model.md`, `docs/architecture/concepts/corpus.md`, `docs/architecture/concepts/document.md` | Model ICP data as corpora rather than app-only JSON: source pages, normalized candidates, scored evidence, prospects, criteria/eval records. |
| Metadata | Stable discovery and retrieval filtering; console metadata tab and SDK `discover_metadata`. | `api/app/api/metadata.py`, `sdk/resources/metadata.py`, `docs/architecture/cross-feature-flow.md` | Store source group, vertical, score components, criteria hash, contact status, feed/pipeline lineage, and use discovery to refine filters. |
| Envelope | Structured `{content, fields, metadata}` output spine for agent/feed/subscription flows. | `docs/architecture/concepts/envelope.md`, `api/app/services/envelope.py` | Agent outputs should be declared-schema envelopes, not only free-text notes. |
| Agents | Preview-gated execution unit with task types `query`, `summarize`, `classify`, `extract`, `review`, `notify`, `custom`; supports declared schema and harvest policy. | `docs/architecture/concepts/agent.md`, `api/app/schemas/agents.py`, `sdk/resources/agents.py` | Use agents for candidate extraction, ICP qualification, prospect extraction, evidence gaps, criteria refinement, and outreach drafting. |
| Feeds | Preview-gated scheduled/reactive process over a source agent; supports persistent target corpus, intervals, UTC cron, backfill, and reactive corpus-change execution. | `docs/architecture/concepts/feed.md`, `api/app/schemas/feeds.py`, `api/app/services/feed_service.py`, `worker/worker/tasks_run_feed.py` | Use scheduled feeds for portfolio/SERP sweeps and reactive feeds when source corpora receive new pages or Apollo data. |
| Pipelines | Preview-gated declarative composition of corpora, agents, feeds, and subscriptions. Current API/service code includes apply, trigger, backfill, pause/resume, and run history. | `api/app/api/pipeline_specs.py`, `api/app/services/pipeline_spec_service.py`, `sdk/resources/pipelines.py` | Represent the ICP growth graph as one versioned PipelineSpec, with traced pipeline runs for manual triggers and backfills. |
| Subscriptions and destinations | Preview routing layer from feed envelopes to agents/destinations with match specs and delivery logs. | `docs/architecture/concepts/subscription.md`, `docs/architecture/destinations.md` | Route only Tier A/B or evidence-gap records to downstream agents or webhooks, and expose delivery failures in the app. |
| Query profiles | Per-corpus saved retrieval defaults and example queries/dataset hints; analysis/optimization workers can tune retrieval defaults. | `docs/architecture/retrieval/query-profiles.md`, `api/app/api/query_profiles.py` | Move best-fit K2 search tuning into corpus query profiles rather than hardcoding weights in the ICP app. |
| Quality and feedback | Online engagement, feedback, gold labels, quality metrics, schema-evolution inputs, and EWMA threshold tuning exist. | `docs/architecture/quality-and-feedback.md`, `sdk/resources/quality.py`, `sdk/resources/search.py` | Use accepted/rejected/exported/replied leads as feedback to improve filters, thresholds, and query profiles. |
| Streams | No separate first-class `Stream` primitive was found comparable to Agent/Feed/Pipeline. Feed outputs are described as envelope streams; MCP has streamable HTTP/SSE plumbing for protocol transport. | `docs/architecture/concepts/feed.md`, `docs/architecture/cross-feature-flow.md`, `api/app/mcp/*` | Treat "streams" for ICP as feed-emitted envelope streams backed by jobs, corpus change events, subscriptions, and destinations. |

## 13. K2-Native ICP Expansion Model

### 13.1 Recommended Corpora

| Corpus | Contents | Key metadata |
| --- | --- | --- |
| `icp-source-corpus` | Portfolio pages, source-list pages, SERP result pages, company home/docs/pricing/blog pages, Apollo organization/person payload summaries. | `entity_type=source_page`, `source_group`, `source_url`, `source_type`, `domain`, `portfolio_parent`, `discovery_query`, `crawl_run_id`, `ingested_at` |
| `icp-candidate-corpus` | One normalized candidate/account record per company/domain. | `entity_type=company`, `company`, `domain`, `vertical`, `source_group`, `criteria_hash`, `dedupe_key`, `candidate_status` |
| `icp-evidence-corpus` | Scoring evidence, AI posture classification, hard-gate results, score components, rationale, citations. | `entity_type=evidence`, `tier`, `total_score`, `ai_posture`, `ai_gap_score`, `data_workflow_score`, `commercial_urgency_score`, `budget_access_score`, `feasibility_score`, `hard_gate_failed`, `hard_gate_unknown` |
| `icp-prospect-corpus` | Apollo people, persona fallbacks, title/role tree, contact confidence, outreach readiness. | `entity_type=prospect`, `prospect_name`, `prospect_title`, `persona_title`, `persona_priority`, `contact_confidence`, `prospect_source`, `outreach_status` |
| `icp-criteria-corpus` | Criteria markdown versions, prompt versions, search-query sets, accepted/rejected examples, gold-label rationale. | `entity_type=criteria`, `criteria_hash`, `criteria_version`, `label_source`, `outcome`, `query_profile_id` |

### 13.2 Recommended Agents

| Agent | K2 task type | Declared output fields |
| --- | --- | --- |
| Source Discovery Agent | `extract` | `company`, `domain`, `category`, `source_group`, `source_url`, `confidence`, `reason` |
| Company Qualification Agent | `classify` or `extract` | `tier`, `total_score`, score components, hard gates, `ai_posture`, `data_workflow_signals`, `evidence_ids` |
| Evidence Gap Agent | `review` | missing evidence fields, recommended crawl/search/Apollo actions, confidence |
| Prospect Role Agent | `extract` | role group, title, person name, LinkedIn/email when legally sourced, persona priority, contact confidence |
| Criteria Refinement Agent | `summarize` or `review` | suggested criteria changes, affected examples, query-profile hint updates, risk notes |
| Outreach Agent | `custom` or `notify` | subject/body/CTA variants, cited evidence, approval status, export metadata |

### 13.3 Scheduled Growth Loop

| Step | Trigger | K2 primitive | Expected result |
| --- | --- | --- | --- |
| 1 | Operator adds source list, portfolio URL, SERP query, CSV, or Apollo seed. | Document ingestion into `icp-source-corpus` with metadata. | Source corpus receives typed source pages/records. |
| 2 | Source corpus changes or daily/weekly schedule fires. | Reactive or scheduled persistent Feed bound to Source Discovery Agent. | New candidate records are written to `icp-candidate-corpus`. |
| 3 | Candidate corpus changes. | Reactive Feed bound to Company Qualification Agent. | Candidate is scored and written to `icp-evidence-corpus`. |
| 4 | Evidence is incomplete or contact path missing. | Subscription match spec routes to Evidence Gap Agent or Prospect Role Agent. | Gaps and prospects are appended with lineage. |
| 5 | Operators accept/reject/export/reply/book meeting. | K2 feedback/engagement/gold-label style records and app state. | Fit outcomes become training/evaluation signals. |
| 6 | Nightly or weekly criteria review runs. | Criteria Refinement Agent plus query profile analysis/optimization. | Proposed search-criteria and query-profile changes are queued for human review. |
| 7 | A source list changes materially or new criteria version is approved. | PipelineSpec backfill in DAG order. | Historical source events are reprocessed under the new criteria hash. |

## 14. Refined Search Criteria For Best-Fit K2 Targets

### 14.1 Core Fit Definition

Best-fit K2 ICP targets are pre-2025 vertical software incumbents with proprietary operational data and workflow ownership, enough budget/reach to buy AI transformation, and either no public AI narrative or a shallow/read-only AI feature that has not yet become a defensible workflow product.

### 14.2 Search And Qualification Signals

| Signal family | Include / boost | Exclude / downrank |
| --- | --- | --- |
| Company age and maturity | Founded before 2025, legacy/established vendor, customer count, operating group/portfolio membership. | Founded in 2025+, stealth startup, generic agency/consulting. |
| Product type | Vertical market software, platform, SaaS, suite, cloud product, API/integration docs. | Services-only, marketplace-only, media/content-only. |
| Workflow/data moat | Work orders, dispatch, trips, diagnostics, claims, inventory, documents, tickets, schedules, transactions, inspections, compliance records. | Generic CRM/content/task tools with little proprietary data. |
| AI posture | No AI, generic AI copy, thin writer/summarizer/chat/search, read-only assistant with limited adoption evidence. | AI-native, agentic platform, foundation model company, AI as primary category. |
| Urgency | Competitive pressure, manual labor workflows, high-cost ops, regulated decisions, customer-experience pressure, PE/portfolio group pressure. | Low-urgency hobby tools or commodity utilities. |
| Budget/access | 25-2,000 employees, funded/profitable, enterprise customers, partner channels, product/engineering/data leaders discoverable. | Too small without funding/ARR, inaccessible contact path. |
| Feasibility | APIs, docs, integrations, permissions, roles, SSO/security, product data model, webhooks. | No technical surface or unclear product architecture. |

### 14.3 K2 Metadata Filters To Standardize

Use these keys consistently across ICP corpora so K2 search and subscription match specs can operate on the same facts:

`entity_type`, `company`, `domain`, `vertical`, `source_group`, `portfolio_parent`, `source_type`, `source_url`, `discovery_query`, `criteria_hash`, `criteria_version`, `tier`, `total_score`, `ai_posture`, `ai_gap_score`, `data_workflow_score`, `commercial_urgency_score`, `budget_access_score`, `feasibility_score`, `hard_gate_failed`, `hard_gate_unknown`, `has_contact_path`, `has_docs_or_api`, `has_pricing_or_commercial`, `prospect_name`, `prospect_title`, `persona_title`, `persona_priority`, `contact_confidence`, `outreach_status`, `feed_id`, `feed_run_at`, `pipeline_run_id`.

### 14.4 Query Profiles To Maintain

| Query profile | Purpose | Example queries / hints |
| --- | --- | --- |
| `portfolio-expansion` | Find more companies like Constellation/Volaris/Harris portfolio accounts. | "vertical market software portfolio companies with workflow data", "operating group software companies automotive fleet maintenance claims" |
| `ai-gap-audit` | Find data-rich accounts with weak AI positioning. | "proprietary workflow data no AI docs", "AI assistant thin feature no pricing no case study" |
| `workflow-moat` | Find strong operational-data categories. | "work orders dispatch diagnostics inspections claims inventory schedules transactions API" |
| `budget-access` | Find companies with enough scale and reachable owners. | "enterprise customers partner channel VP product CTO data leader 25 2000 employees" |
| `prospect-role-tree` | Find people/contact records by role hierarchy. | "chief product officer VP engineering head of data general manager vertical product" |

Each profile should start with explicit example queries and dataset hints from `icp.md`, then be tuned from accepted/rejected/exported/replied outcomes.
