# E2E Test Plan: Agentic GTM Dashboard

## Surface Map

The dashboard is a static HTML/CSS/JS app served by `icp_engine.web` at `/`.
It has no separate frontend package or router. Navigation is tab-based inside a
single page:

| Area | Selector / Endpoint | Purpose |
| ---- | ------------------- | ------- |
| Discover sidebar | `#run-form`, `/api/search`, `/api/runs` | Candidate discovery, enrichment, and scoring launch |
| Leads | `button.tab[data-view='leads']`, `#lead-rows` | Lead list and detail inspection |
| Prospects | `button.tab[data-view='prospects']`, `/api/runs/:id/prospects` | Persona/Apollo reach-out targets |
| Research | `button.tab[data-view='research']`, `/api/research` | Natural-language run research |
| K2 | `button.tab[data-view='k2']`, `/api/runs/:id/k2-manifest` | Manifest preview/export/sync |
| Setup | `button.tab[data-view='setup']`, `/api/state` | Seeded prompts, settings, account lists, and verticals |
| Criteria | `button.tab[data-view='criteria']`, `/api/criteria` | ICP markdown configuration |

Auth is optional bearer-token auth through `ICP_ADMIN_TOKEN`. The smoke runner
uses an isolated local server with auth disabled and a temporary state directory.

## Coverage Matrix

| ID | Type | Priority | Flow | Preconditions | Validation |
| -- | ---- | -------- | ---- | ------------- | ---------- |
| TC-001 | smoke | P0 | Dashboard loads a seeded run and renders Leads | Isolated server started; one run seeded with deterministic evidence | UI heading, lead rows, no console errors |
| TC-002 | smoke | P0 | Prospects tab renders persona targets | TC-001 seed run exists | UI prospect row, API state has one lead |
| TC-003 | flow | P0 | Research tab answers a GTM question with metadata-backed brief | TC-001 seed run exists | UI answer contains brief, metadata, matched leads, citations; API `/api/research` returns `metadata_used` |
| TC-004 | smoke | P1 | K2 manifest preview renders metadata payload | TC-001 seed run exists | UI manifest preview includes document metadata |
| TC-005 | smoke | P1 | Criteria editor renders active markdown | TC-001 server state initialized | UI criteria textarea is populated |
| TC-006 | smoke | P1 | Setup tab renders seeded prompts/settings/lists | TC-001 server state initialized | UI setup grid includes discovery prompt, seeded account list, deployment mode; API state includes prompts/settings/lists |

## Runner

Run:

```bash
make e2e-smoke
```

The runner starts `python3 -m icp_engine.web` on the configured local port,
seeds deterministic evidence through the Python application layer, exercises the
browser with Playwright, validates `/api/state` and `/api/research`, and writes
a JSON report to `out/e2e/dashboard-smoke-report.json`.
