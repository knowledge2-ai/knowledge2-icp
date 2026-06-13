# Tech Design: ICP Evaluation Pipeline

<!--
METADATA (agent-parseable):
design_id: 2026-06-13-icp-eval-pipeline
date: 2026-06-13
status: Draft
services_affected: icp_engine, deployment/cloudflare, K2 dev project
stacks: Python, JavaScript, Cloudflare Worker, K2 API
total_work_items: 9
estimated_total_effort: 5-8 days
-->

**Date:** 2026-06-13
**Author:** AI Architect Agent
**Status:** Draft
**Stakeholders:** GTM operators, ICP owner, K2 platform owner
**Services affected:** `icp_engine`, `deployment/cloudflare`, K2 dev project
**Tech stacks:** Python, JavaScript, Cloudflare Worker, K2 API

## 1. Executive Summary

The ICP app should not create a separate evaluation platform first. K2 already has retrieval eval runs, quality metrics, feedback, gold labels, query logs, extraction evaluators, generated eval sets, and console quality surfaces. The ICP app should use those as the quality system of record and add an ICP-specific evaluator layer for business objects that K2 retrieval evals do not natively understand yet: account qualification, prospect role trees, source coverage, criteria calibration, and outreach readiness.

The recommended design is a K2-first evaluation pipeline with a thin local/Worker runner. Local app state stores eval cases and run summaries for demo continuity, while K2 receives durable feedback, metadata, quality signals, and eval artifacts. Langfuse, Phoenix, Ragas, or DeepEval should remain optional adapters, not the primary store, unless we need trace dashboards or LLM-as-judge metrics before K2 exposes equivalent surfaces for this app.

### Key decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| D-1 | Use K2 quality/eval/feedback as the system of record. | K2 already exposes `quality`, `feedback`, `evaluation`, `GoldLabel`, `RetrievalOutcome`, and `EvalRun` primitives. |
| D-2 | Add an ICP-specific eval runner in this repo. | K2 retrieval eval scores query/chunk behavior; ICP also needs company, criteria, prospect, and source-quality checks. |
| D-3 | Keep OSS eval frameworks optional. | Langfuse/Phoenix are useful for trace UX, and Ragas/DeepEval for judge metrics, but adopting them now would duplicate K2 quality state. |

## 2. Requirements & Context

### 2.1 Problem statement

The ICP system now loads hundreds of companies and produces scored leads, role-tree prospects, research answers, K2 manifests, and source scans. There is no repeatable quality gate proving that loaded data is complete, produced results are useful, criteria are calibrated, and K2-backed research stays grounded over time.

### 2.2 Functional requirements

| ID | Requirement | Priority | Acceptance criteria |
|----|-------------|----------|---------------------|
| FR-1 | Store versioned ICP eval cases for companies, sources, prospects, research questions, and criteria examples. | Must | Eval cases persist locally and can be mirrored into K2 metadata with `criteria_hash`, `source`, `expected`, and `label_source`. |
| FR-2 | Evaluate loaded data quality. | Must | Runner reports source coverage, duplicate domains, required metadata completeness, stale evidence, and prospect/contact completeness. |
| FR-3 | Evaluate produced ICP results. | Must | Runner scores account tier correctness, hard-gate correctness, role-tree quality, citation coverage, and research answer groundedness. |
| FR-4 | Feed accepted/rejected/exported/replied outcomes into K2 feedback/quality loops. | Should | Operator workflow actions become K2 feedback or gold-label records where compatible. |
| FR-5 | Add deploy gates and dashboard summaries. | Should | E2E validation can fail when seeded gold accounts regress; UI exposes latest eval status and deltas. |
| FR-6 | Support optional OSS trace/eval adapters. | Could | If enabled, traces and scores can be emitted to Langfuse or Phoenix without changing K2/local canonical records. |

### 2.3 Non-functional requirements

| ID | Requirement | Target | Current | Acceptance criteria |
|----|-------------|--------|---------|---------------------|
| NFR-1 | Repeatability | Same eval case version and run input produce comparable metric keys. | No eval case store. | Eval run includes `case_set_hash`, `criteria_hash`, and code version. |
| NFR-2 | Lineage | Every score links to source data and criteria. | Run metadata has partial lineage. | Eval result stores `run_id`, `domain`, `source_id`, `criteria_hash`, and evidence IDs. |
| NFR-3 | Cost control | LLM judges are optional and budgeted. | Provider guardrails exist in this branch. | Eval runner honors provider limits before LLM/judge calls. |
| NFR-4 | Privacy | Contact data does not leave approved systems by default. | Apollo contacts can be stored/exported. | OSS adapter redacts email/phone unless explicitly enabled. |

## 3. Current State Assessment

### 3.1 Local ICP app

The local app has seeded accounts, source scans, lead workflow state, account details, prospects, K2 sync, criteria versions, and audit logs. Relevant files are `icp_engine/app_store.py`, `icp_engine/web.py`, `icp_engine/research.py`, `icp_engine/scoring.py`, `icp_engine/prospects.py`, `icp_engine/k2_sync.py`, `deployment/cloudflare/worker.js`, and `tests/e2e/run_dashboard_smoke.py`.

### 3.2 K2 eval and quality primitives found

| Primitive | Evidence | ICP implication |
|-----------|----------|-----------------|
| Offline eval runs | `/Users/antonmishel/k2/k2_mvp/api/app/api/evaluation.py`, `docs/architecture/ml/evaluation.md`, `docs/architecture/concepts/evaluation-run.md` | Use for retrieval/query-set quality where ICP data is indexed in K2. |
| Quality metrics | `/Users/antonmishel/k2/k2_mvp/api/app/api/quality.py`, `api/app/services/quality_metrics_service.py`, `docs/architecture/quality-and-feedback.md` | Use for live K2 corpus health, engagement, routing, and filter quality. |
| Feedback | `/Users/antonmishel/k2/k2_mvp/api/app/api/feedback.py`, `sdk/resources/search.py` | Map accepted/rejected/exported/replied outcomes into feedback signals. |
| Gold labels | `k2_core/db/models.py` and `docs/architecture/quality-and-feedback.md` | Store curated "Mojio should qualify" style examples as durable labels. |
| Synthetic eval sets | `worker/worker/tasks_eval_set.py`, `worker/worker/analysis/evaluation.py` | Bootstrap query evals when hand labels are sparse. |
| Extraction evaluator | `k2_core/extraction_evaluator.py`, `tests/worker/test_extraction_evaluator.py` | Reuse pattern for structured field validation; add ICP-specific field checks. |
| Console quality UI | `console_frontend/src/components/quality/QualityDashboard.jsx`, `docs/integrators/console/eval-and-quality.md` | K2 already has quality UX; ICP app should summarize, not duplicate, deeper K2 console screens. |

Important constraint: K2's public API reference currently exposes list/get eval runs, while create/upload eval endpoints are internal-worker only and feature-gated by `finetuning_enabled`. The ICP runner should therefore start by recording local eval runs and K2 feedback/quality-compatible artifacts, then use native K2 eval-run creation only where the K2 dev project exposes it.

## 4. High-Level Design

### 4.1 Architecture diagram

```text
ICP sources / runs / prospects / criteria
        |
        v
ICP Eval Runner
  - deterministic validators
  - optional LLM judge adapters
  - K2 quality/feedback mapper
        |
        +--> local app state: eval_cases.json, eval_runs.json
        +--> K2 corpora metadata: eval_case, eval_result, feedback_signal
        +--> K2 feedback/quality APIs where compatible
        +--> optional Langfuse/Phoenix traces or Ragas/DeepEval scores
        |
        v
Dashboard + deploy gate
  - current quality summary
  - regression warnings
  - criteria refinement suggestions
```

### 4.2 Evaluation layers

| Layer | What is evaluated | Metrics |
|-------|-------------------|---------|
| Data load | Source scans, candidate list, seeded accounts, K2 manifests | unique domains, duplicate rate, required metadata completeness, source coverage, stale evidence rate |
| Qualification | Lead tier, total score, hard gates, rationale | gold label pass rate, accepted/rejected precision proxy, score drift, hard-gate disagreement |
| Prospect tree | Role groups, people, titles, contact source, confidence | role coverage, named contact rate, contact confidence distribution, missing buyer persona rate |
| Research/RAG | Local/K2 answers and citations | citation coverage, grounded answer rate, K2 `recall@k`/`mrr@k` where eval runs are available |
| Criteria refinement | Criteria version against known examples | promoted/demoted account count, threshold sensitivity, query-profile hint drift |
| Outreach readiness | Drafts and export packages when implemented | evidence-backed personalization rate, approval rate, compliance warnings |

### 4.3 Data model changes

New local state files:

```text
out/app_state/eval_cases.json
out/app_state/eval_runs.json
```

Eval case shape:

```json
{
  "id": "case-mojio-tier-a",
  "type": "qualification",
  "domain": "moj.io",
  "company": "Mojio",
  "input_ref": {"run_id": "run-seeded-icp", "source": "seed"},
  "expected": {"tier": "A", "hard_gate_failed": false},
  "criteria_hash": "optional",
  "label_source": "expert_labeled",
  "created_at": "2026-06-13T00:00:00+00:00"
}
```

Eval result shape:

```json
{
  "id": "eval-20260613-001",
  "case_set_hash": "abc123",
  "run_id": "run-seeded-icp",
  "criteria_hash": "abc123",
  "status": "succeeded",
  "metrics": {
    "qualification_pass_rate": 0.94,
    "source_metadata_completeness": 0.88,
    "prospect_role_coverage": 0.71,
    "citation_coverage": 0.83
  },
  "failures": []
}
```

K2 mirror metadata:

`entity_type`, `eval_case_id`, `eval_result_id`, `eval_type`, `domain`, `company`, `criteria_hash`, `criteria_version`, `source_id`, `run_id`, `feed_id`, `pipeline_run_id`, `label_source`, `expected_tier`, `actual_tier`, `metric_name`, `metric_value`, `pass`.

### 4.4 API changes

```text
GET  /api/evals/cases
POST /api/evals/cases
GET  /api/evals/runs
POST /api/evals/runs
GET  /api/evals/summary
POST /api/runs/{run_id}/leads/{domain}/feedback
```

The first implementation can keep these local/Worker-backed. K2 sync then maps the records into the K2 corpora and APIs that are available in dev.

## 5. Low-Level Design

### 5.1 Module structure

```text
icp_engine/evals.py                 # case/result models and deterministic metrics
icp_engine/eval_store.py            # AppStore-facing helpers, or methods on AppStore
icp_engine/k2_eval_sync.py          # K2 feedback/gold-label/eval artifact mapper
icp_engine/web.py                   # /api/evals endpoints
deployment/cloudflare/worker.js     # seeded Worker mirror
tests/test_evals.py                 # deterministic unit tests
tests/test_web.py                   # API smoke coverage
tests/e2e/run_dashboard_smoke.py    # dashboard eval summary smoke
```

### 5.2 Key abstractions

```python
class IcpEvalRunner:
    def run(self, *, run_id: str, case_ids: list[str] | None = None) -> IcpEvalRun:
        """Evaluate loaded data and produced results for a run."""

class IcpEvalMetric:
    name: str
    value: float
    threshold: float
    passed: bool
    failures: list[dict]

class K2EvalSignalMapper:
    def map_feedback(self, lead_state: dict) -> list[dict]:
        """Convert operator workflow outcomes into K2 feedback-compatible records."""
```

### 5.3 Error handling

| Scenario | Response | Recovery |
|----------|----------|----------|
| Missing run | `404` with `Run not found` | Operator selects an existing run. |
| Missing eval cases | Create default seeded cases from `icp.md` and `seed-companies.json` | Cases can be edited later. |
| K2 eval API not feature-enabled | Local eval succeeds with `k2_status=skipped_feature_not_enabled` | Retry after K2 feature flag is enabled. |
| LLM judge over budget | Deterministic metrics still run, judge metrics marked skipped | Increase provider limit or disable judge. |
| OSS adapter unavailable | K2/local records still complete | Adapter is non-blocking. |

## 6. Options Considered

### Option A: K2-first ICP eval runner (Recommended)

Use local deterministic evaluators for ICP business objects, mirror artifacts to K2, and call K2 quality/feedback/eval APIs when available.

Pros: aligns with K2 primitives, avoids duplicate systems of record, works in Cloudflare/local demo, supports later K2-native PipelineSpec execution.

Cons: requires a small custom evaluator for account/prospect/business metrics.

Effort: M/L.

### Option B: Langfuse or Phoenix as primary eval store

Emit all ICP traces and scores to an OSS observability platform, then optionally backfill K2.

Pros: strong trace UX, online/offline eval workflow, datasets, experiments, and score dashboards.

Cons: duplicates K2 quality state, introduces another deploy surface, and adds privacy/compliance work for contact data.

Effort: L.

### Option C: DeepEval/Ragas-only test suite

Keep evals as CI tests and local reports.

Pros: fast to add and useful for LLM judge metrics.

Cons: weak production feedback loop and no durable GTM/operator dashboard unless we build one anyway.

Effort: S/M.

## 7. OSS Package Evaluation

No OSS eval package is required for the first implementation. If K2 lacks trace UI or LLM judge metrics for a needed flow, use adapters in this order:

| Package | Purpose | License/adoption note | Verdict |
|---------|---------|-----------------------|---------|
| Langfuse | Tracing, datasets, experiments, online/offline scores | Official docs describe trace scoring, datasets, experiments, CI/CD checks, and self-hosting. | Optional adapter for trace UX. |
| Phoenix | OpenTelemetry-based AI observability and evaluation | Official docs describe traces, evaluations, datasets, prompt experiments, and human annotations. | Optional adapter if OTEL/OpenInference is preferred. |
| Ragas | RAG and agent metrics | Official docs list RAG metrics such as context precision/recall, faithfulness, and agent tool metrics. | Optional metric runner for research/RAG answers. |
| DeepEval | Pytest-like local LLM evals | Official docs show local `deepeval test run`, custom G-Eval, tracing, and datasets. | Optional CI runner for prompt/outreach/research regressions. |

## 8. Cross-Cutting Concerns

### 8.1 Security

Eval records can include person names, titles, emails, LinkedIn URLs, and Apollo provenance. Default K2/local records should store contact confidence and source references, but OSS adapter payloads must redact direct contact fields unless `ICP_EVAL_EXPORT_PII=true`.

### 8.2 Scalability

The first runner should evaluate hundreds to low thousands of accounts synchronously or as a short background job. For larger discovery volumes, move eval execution into K2 feeds/pipelines or a GKE worker.

### 8.3 Observability

Every eval run should append audit events and expose summary metrics in `/api/state`. K2 sync should include `eval_run_id` and `case_set_hash` metadata so K2 search can retrieve quality history by domain, source, criteria, and pipeline run.

### 8.4 Reliability

Deterministic metrics are mandatory; LLM judge metrics and OSS export are best-effort. Failed optional steps must not hide deterministic failures.

## 9. Affected Areas

### 9.1 Code changes

| File/Module | Change type | Description | Work item |
|-------------|-------------|-------------|-----------|
| `icp_engine/evals.py` | New | Eval case/result models and deterministic metric runner. | WI-1 |
| `icp_engine/app_store.py` | Modify | Persist eval cases/runs and expose summary state. | WI-2 |
| `icp_engine/web.py` | Modify | Add eval and feedback endpoints. | WI-3 |
| `icp_engine/k2_eval_sync.py` | New | Map eval cases/results/outcomes to K2 feedback and metadata. | WI-4 |
| `deployment/cloudflare/worker.js` | Modify | Mirror seeded eval endpoints and summary. | WI-5 |
| `icp_engine/web_assets/app.js` | Modify | Add Eval/Quality dashboard panel. | WI-6 |
| `tests/test_evals.py` | New | Unit tests for metrics and case hashing. | WI-7 |
| `tests/test_web.py` | Modify | API coverage for eval endpoints. | WI-7 |
| `tests/e2e/run_dashboard_smoke.py` | Modify | E2E coverage for summary and regression warning. | WI-8 |

### 9.2 Documentation changes

| Document | Change needed | Work item |
|----------|---------------|-----------|
| `README.md` | Document eval commands, API, and K2 sync behavior. | WI-9 |
| `docs/CLOUDFLARE_K2_DEPLOYMENT.md` | Add deploy validation and live eval gate. | WI-9 |

## 10. Implementation Work Items

### 10.1 Work item registry

| ID | Title | Phase | Type | Service | Files | Depends on | Effort | Reqs covered |
|----|-------|-------|------|---------|-------|------------|--------|--------------|
| WI-1 | Add deterministic ICP eval runner | 1 | code | ICP app | `icp_engine/evals.py` | - | M | FR-1, FR-2, FR-3 |
| WI-2 | Persist eval cases and runs | 1 | code | ICP app | `icp_engine/app_store.py` | WI-1 | S | FR-1 |
| WI-3 | Add eval API endpoints | 1 | code | ICP app | `icp_engine/web.py` | WI-1, WI-2 | S | FR-1, FR-5 |
| WI-4 | Add K2 eval signal mapper | 2 | code | K2 integration | `icp_engine/k2_eval_sync.py`, `icp_engine/k2_client.py` | WI-2 | M | FR-4 |
| WI-5 | Mirror eval support in Worker | 2 | code | Cloudflare | `deployment/cloudflare/worker.js` | WI-3 | M | FR-5 |
| WI-6 | Add quality dashboard panel | 3 | code | UI | `icp_engine/web_assets/app.js`, `icp_engine/web_assets/styles.css` | WI-3 | M | FR-5 |
| WI-7 | Add unit/API tests | 3 | test | ICP app | `tests/test_evals.py`, `tests/test_web.py` | WI-1, WI-3 | S | FR-1, FR-2, FR-3 |
| WI-8 | Add E2E eval smoke | 3 | test | E2E | `tests/e2e/run_dashboard_smoke.py` | WI-6 | S | FR-5 |
| WI-9 | Document eval operations | 3 | docs | Docs | `README.md`, `docs/CLOUDFLARE_K2_DEPLOYMENT.md` | WI-5 | XS | FR-5, FR-6 |

### 10.2 Work item details

#### WI-1: Add deterministic ICP eval runner

- **Description:** Create a runner that evaluates source coverage, qualification correctness, prospect role coverage, citation coverage, and criteria drift from existing run data and eval cases.
- **Acceptance criteria:**
  - [ ] Can run against `run-seeded-icp`.
  - [ ] Computes deterministic metrics without provider calls.
  - [ ] Fails known seeded regressions such as missing Mojio or wrong ServiceTitan score tier.
  - [ ] Tests pass: `python3 -m pytest tests/test_evals.py`.

#### WI-2: Persist eval cases and runs

- **Description:** Add AppStore persistence for eval cases and results with stable case-set hashing.
- **Acceptance criteria:**
  - [ ] Empty state seeds a minimal gold set from committed data.
  - [ ] Eval run history survives restart locally.
  - [ ] `/api/state` includes current eval summary.

#### WI-3: Add eval API endpoints

- **Description:** Add REST endpoints for listing cases, creating cases, running evals, and reading summaries.
- **Acceptance criteria:**
  - [ ] Admin token protects mutating eval endpoints when configured.
  - [ ] Denied provider/judge calls return visible budget reasons.
  - [ ] API tests cover success and failure.

#### WI-4: Add K2 eval signal mapper

- **Description:** Convert ICP workflow outcomes and eval artifacts into K2 feedback, metadata documents, and quality-compatible signals.
- **Acceptance criteria:**
  - [ ] Accepted/Qualified/Exported map to positive signals.
  - [ ] Rejected maps to negative signal with reason metadata.
  - [ ] K2 feature-gate failures are visible and non-destructive.

#### WI-5: Mirror eval support in Worker

- **Description:** Add seeded eval cases, run summaries, and API compatibility in `deployment/cloudflare/worker.js`.
- **Acceptance criteria:**
  - [ ] Live Worker can report seeded eval summary without local server.
  - [ ] Worker tests and `node --check` pass.

#### WI-6: Add quality dashboard panel

- **Description:** Add an Eval/Quality panel with latest run, trend, failures, source coverage, and K2 sync status.
- **Acceptance criteria:**
  - [ ] Operators can see why a run failed quality.
  - [ ] UI does not hide deterministic metrics when optional LLM judge is skipped.

#### WI-7: Add unit/API tests

- **Description:** Cover eval metric calculations, persistence, API contracts, and K2 mapper shape.
- **Acceptance criteria:**
  - [ ] Unit tests cover pass/fail thresholds and case hashing.
  - [ ] API tests cover missing run and seeded success paths.

#### WI-8: Add E2E eval smoke

- **Description:** Extend dashboard smoke to validate eval summary visibility and seeded pass state.
- **Acceptance criteria:**
  - [ ] E2E smoke fails if seeded eval summary is missing.
  - [ ] Screenshots remain usable on desktop and mobile.

#### WI-9: Document eval operations

- **Description:** Document local command, API usage, K2 sync, and optional OSS adapter posture.
- **Acceptance criteria:**
  - [ ] README explains how to run and interpret evals.
  - [ ] Deployment doc includes live eval validation before declaring success.

### 10.3 Phase summary

| Phase | Description | Work items | Prerequisites | Phase effort |
|-------|-------------|------------|---------------|--------------|
| 1 | Local deterministic eval spine | WI-1, WI-2, WI-3 | None | 1-2 days |
| 2 | K2/Worker integration | WI-4, WI-5 | Phase 1 | 2-3 days |
| 3 | UI, tests, docs | WI-6, WI-7, WI-8, WI-9 | Phase 2 | 2-3 days |

### 10.4 Rollout plan

1. Ship deterministic local/Worker evals behind existing admin auth.
2. Add K2 mirror writes in dry-run mode first.
3. Enable K2 feedback writes for lead outcomes.
4. Add optional OSS adapter only after a concrete trace/eval gap is confirmed.
5. Make seeded eval pass a deploy validation step.

### 10.5 Rollback plan

Disable eval endpoints from the UI and skip K2 eval sync. Existing run, lead, source, and criteria state remains unaffected because eval records are additive.

### 10.6 Testing strategy

| Test type | What to test | Framework/approach | Work item |
|-----------|--------------|--------------------|-----------|
| Unit | Metric calculations, thresholds, case hashing | `pytest` | WI-7 |
| API | Eval endpoints, auth, missing run, budget denial | `pytest` + local HTTP server | WI-7 |
| E2E | Dashboard quality summary and seeded pass state | Playwright smoke runner | WI-8 |
| Live deploy | Worker health, state, seeded eval summary | `curl`/scripted validation | WI-9 |

## 11. Risks & Open Issues

### 11.1 Risks

| ID | Risk | Likelihood | Impact | Mitigation | Affected work items |
|----|------|------------|--------|------------|---------------------|
| R-1 | K2 eval creation remains internal/feature-gated in dev. | Medium | Medium | Start with local eval runs and K2 feedback/metadata mirror. | WI-4 |
| R-2 | LLM judge metrics become expensive or noisy. | Medium | Medium | Deterministic metrics are required; LLM judges are optional and budgeted. | WI-1 |
| R-3 | Contact PII leaks to OSS tracing. | Low | High | Redact by default; require explicit env opt-in. | WI-4 |
| R-4 | Operator feedback is noisy. | Medium | Medium | Separate `expert_labeled`, `operator_feedback`, and `derived_engagement` sources. | WI-4 |

### 11.2 Open questions

| ID | Question | Owner | Deadline | Blocks | Resolution |
|----|----------|-------|----------|--------|------------|
| Q-1 | Should K2 expose public eval-run create for this project, or should ICP use internal K2 jobs only through PipelineSpec? | K2 owner | Before WI-4 | WI-4 | Pending |
| Q-2 | Which outcome is authoritative for fit: Qualified, Exported, replied, meeting booked, or closed-won? | ICP owner | Before criteria tuning | None | Pending |
| Q-3 | Is Langfuse/Phoenix desired for trace UX, or is K2 console quality sufficient? | Product/K2 owner | Before OSS adapter | None | Pending |

### 11.3 Assumptions

| ID | Assumption | Validated? | Evidence | If invalidated |
|----|------------|------------|----------|----------------|
| A-1 | K2 should remain the system of record for quality. | Yes | K2 has `quality`, `feedback`, `evaluation`, `GoldLabel`, and console quality surfaces. | Revisit Langfuse/Phoenix primary store. |
| A-2 | ICP business-object evals are not fully covered by K2 retrieval eval. | Yes | K2 eval docs focus on query/chunk retrieval metrics. | Use K2 native eval directly if schema is expanded. |
| A-3 | Deterministic seeded evals can catch current demo regressions. | Yes | Committed 428-account seed and run data include known accounts and scores. | Add hand-authored cases. |

## 12. Decision Log

| ID | Date | Decision | Context | Alternatives rejected | Affects |
|----|------|----------|---------|----------------------|---------|
| D-1 | 2026-06-13 | Use K2 as eval/quality system of record. | User asked to explore K2 evals and OSS fallback. | Langfuse/Phoenix primary store. | WI-4 |
| D-2 | 2026-06-13 | Add local ICP-specific eval runner. | K2 retrieval eval does not score full GTM business objects. | K2-only retrieval eval. | WI-1 |
| D-3 | 2026-06-13 | Keep OSS adapters optional. | Avoid duplicated state and contact-data exposure. | Immediate Langfuse deployment. | WI-4, WI-9 |

## Appendix A: Validation Evidence

Local evidence inspected:

```text
/Users/antonmishel/k2/k2_mvp/AGENTS.md
/Users/antonmishel/k2/k2_mvp/docs/architecture/quality-and-feedback.md
/Users/antonmishel/k2/k2_mvp/docs/architecture/concepts/evaluation-run.md
/Users/antonmishel/k2/k2_mvp/docs/architecture/concepts/quality-run.md
/Users/antonmishel/k2/k2_mvp/docs/architecture/ml/evaluation.md
/Users/antonmishel/k2/k2_mvp/docs/integrators/console/eval-and-quality.md
/Users/antonmishel/k2/k2_mvp/docs/integrators/reference/api/evaluation.md
/Users/antonmishel/k2/k2_mvp/docs/integrators/reference/api/quality.md
/Users/antonmishel/k2/k2_mvp/api/app/api/evaluation.py
/Users/antonmishel/k2/k2_mvp/api/app/api/quality.py
/Users/antonmishel/k2/k2_mvp/api/app/api/feedback.py
/Users/antonmishel/k2/k2_mvp/sdk/resources/quality.py
/Users/antonmishel/k2/k2_mvp/sdk/resources/search.py
/Users/antonmishel/k2/k2_mvp/k2_core/extraction_evaluator.py
```

## Appendix B: References

| Source | URL | Relevance |
|--------|-----|-----------|
| Langfuse evaluation overview | https://langfuse.com/docs/evaluation/overview | Confirms online/offline evals, datasets, experiments, scores, and CI/CD checks. |
| Ragas available metrics | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ | Confirms RAG and agent metrics useful for optional judge layer. |
| Arize Phoenix docs | https://arize.com/docs/phoenix | Confirms OTEL tracing, evaluations, datasets, experiments, and annotations. |
| DeepEval quickstart | https://deepeval.com/docs/getting-started | Confirms pytest-like local eval runner and custom G-Eval support. |

## Appendix C: Agent Parsing Guide

Planning agents should parse Section 10.1 for the implementation DAG, Section 10.2 for acceptance criteria, Section 9 for affected files, and Section 11 for risks and open questions.

