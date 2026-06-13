# UI Review Plan

## Application Overview

Knowledge2 ICP is a single-page Agentic GTM dashboard for BDRs, GTM operators, and ICP owners. It helps users discover candidate accounts, qualify them against the K2 ICP, inspect prospects and evidence, manage sources, review K2 sync/workspace health, run evals, and edit criteria/settings.

Frontend stack: static HTML (`icp_engine/web_assets/index.html`), vanilla JavaScript (`icp_engine/web_assets/app.js`), custom CSS (`icp_engine/web_assets/styles.css`), served by `icp_engine.web` locally and a Cloudflare Worker in production. There is no React/Vue package, router, or component library.

## Target Users

- BDR/GTM operator: works queue-style, needs fast account triage, account context, contacts, next-best action, outreach drafts, exports, and objection/evidence context.
- ICP owner: edits criteria, reviews fit/quality, tunes source and provider settings, and tracks score drift.
- Platform/operator: monitors K2, providers, rate limits, and eval health before running automation.

## Authentication Strategy

Local screenshot capture uses the loopback server without `ICP_ADMIN_TOKEN`, which is supported by `icp_engine.web` for local-only use. Live Cloudflare uses short-lived admin sessions, but this review captures local UI state to avoid exposing live secrets and to keep screenshots reproducible.

## Data Seeding Strategy

Use an isolated local state directory. The default `AppStore` returns the committed seeded state when no run files exist:

- latest run: `run-seeded-icp`
- leads: 428 accounts, including Constellation/Volaris/Harris and named ICP examples
- evidence: populated seed evidence per account
- sources: 3 seeded discovery sources
- prompts/settings/lists: seeded under `/api/state`

No external providers are required for screenshots. The capture session may mutate only the isolated local state.

## Route Inventory

The app has one browser route and tab-based in-page navigation.

| # | Route pattern | Page component | Dynamic segments | Requires data |
|---|---|---|---|---|
| 1 | `/` | `icp_engine/web_assets/index.html` SPA shell | none | yes |
| 2 | `/api/state` | API state endpoint used by frontend | none | yes |
| 3 | `/api/runs/:id/accounts/:domain` | Account detail API used by Prospects tab | run id, domain | yes |
| 4 | `/api/runs/:id/prospects` | Prospect API used by Prospects tab | run id | yes |
| 5 | `/api/k2-workspace` | K2 workspace status API | none | optional K2 credentials |
| 6 | `/api/evals/runs` | Eval runner API | none | yes |

## In-Page States Inventory

| Route | Trigger | State name | Screenshot scenario |
|---|---|---|---|
| `/` | Initial load | Leads queue | `01_core_dashboard`, step 3 |
| `/` | Click first lead row | Account drilldown / prospect focus | `01_core_dashboard`, step 5 |
| `/` | Click Sources tab | Source manager | `02_sources_and_research`, step 2 |
| `/` | Click Research tab and ask question | Research answer | `02_sources_and_research`, step 7 |
| `/` | Click K2 tab and workspace status | K2 workspace status | `03_ops_quality_setup`, step 3 |
| `/` | Click Evals tab and run eval | Eval summary | `03_ops_quality_setup`, step 7 |
| `/` | Click Setup tab | Settings/lists/prompts | `03_ops_quality_setup`, step 10 |
| `/` | Click Criteria tab | Criteria editor | `04_criteria_runs_empty`, step 2 |
| `/` | Click Runs tab | Run history | `04_criteria_runs_empty`, step 5 |
| `/` | Apply impossible lead filter | Empty lead queue | `04_criteria_runs_empty`, step 8 |

## Scenario Design

The scenario JSON captures four flows:

1. Core BDR queue and account drilldown.
2. Source manager and research answer.
3. K2, eval, and setup/operator surfaces.
4. Criteria, runs, and a no-results empty state.

Mobile screenshots are captured with the same scenario file by rerunning the capture with mobile viewport overrides into a mobile subdirectory.

## Variables

| Variable | Source | Used for |
|---|---|---|
| `base_url` | capture command / scenario setting | local app URL |
| `run_id` | seeded app state, indirectly through UI | Account/prospect/eval flows |

## Capture Checklist

- [x] All top-level tabs.
- [x] Populated state using seeded run.
- [x] Account drilldown and prospect tree.
- [x] Research answer with citations.
- [x] K2 workspace health state.
- [x] Eval summary state.
- [x] Criteria editor and version controls.
- [x] Empty lead queue state.
- [x] Mobile viewport capture for key screens.
