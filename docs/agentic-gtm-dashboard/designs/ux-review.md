# UX Review: Agentic GTM Dashboard

## Target Users

- GTM operators running repeated account-discovery workflows.
- Sales/research users reviewing account evidence, prospects, and outreach angles.
- Platform/admin operators configuring ICP criteria, provider keys, K2 sync, and deployment settings.

The dashboard should behave like a dense operations console: fast to scan, low ceremony, strong table readability, and clear separation between local/dry-run actions and production mutations.

## Evidence Captured

Original screenshots:

- `screenshots/original/01_leads.jpg`
- `screenshots/original/02_prospects.jpg`
- `screenshots/original/03_research.jpg`
- `screenshots/original/04_k2.jpg`
- `screenshots/original/05_k2_manifest.jpg`
- `screenshots/original/06_criteria.jpg`
- `screenshots/original/07_candidate_preview.jpg`

Wireframe artifacts:

- `screenshots/wireframes/wireframe_dashboard.jpg`
- `screenshots/wireframes/wireframe_prospects.jpg`
- `screenshots/wireframes/wireframe_k2.jpg`
- `screenshots/wireframes/wireframe_research_criteria.jpg`

Capture plan:

- `../plans/ui-review-plan.md`
- `../plans/ui-review-scenarios.json`
- `../plans/ui-review-candidate-preview.json`

## Current State Assessment

The app uses a static HTML/CSS/JS frontend served by `icp_engine.web`. Navigation is a left discovery rail plus horizontal tabs for Leads, Prospects, Research, K2, Criteria, and Runs. The visual language is appropriately operational: restrained colors, compact controls, no decorative marketing layout.

The review found two rendered layout issues and two launch-safety issues. The table/manifest layout defects were fixed during this review and verified by recapture. The production-safety items were also addressed by adding focus-visible styling and K2 apply confirmation. Later recaptures verified the added Active Criteria lead-detail section and metadata-backed Research answer render without overlap in the existing desktop layout.

## Findings

| ID | Severity | Status | Evidence | Affected Files | Finding | Resolution / Next Step |
|----|----------|--------|----------|----------------|---------|------------------------|
| V-001 | Major | Fixed | `01_leads.jpg` | `icp_engine/web_assets/styles.css` | Lead table strategy text could clip because fixed minimum grid columns exceeded available table width. | Reduced fixed tier/score columns and allowed strategy to shrink/wrap. Recaptured screenshot shows the strategy text readable. |
| V-002 | Major | Fixed | `05_k2_manifest.jpg` | `icp_engine/web_assets/styles.css` | K2 JSON metadata preview could overflow horizontally on long values. | Added `white-space: pre-wrap` and `overflow-wrap: anywhere` to `.manifest-preview`. |
| V-003 | Minor | Fixed | `02_prospects.jpg` | `icp_engine/web_assets/app.js` | Prospects table exposed raw enum text like `persona_target`, which wrapped poorly and looked implementation-specific. | Added `prospectContactLabel()` so strategy fallback rows show `Persona`. |
| V-004 | Major | Fixed | K2 apply workflow | `icp_engine/web_assets/app.js` | `Apply sync` is a live remote mutation path and previously had no confirmation step. | Added a browser confirmation before `apply=true` K2 sync. |
| V-005 | Major | Fixed | Keyboard accessibility review | `icp_engine/web_assets/styles.css` | Custom controls had hover states but no explicit `:focus-visible` styling. | Added a visible 3px focus outline for buttons, inputs, selects, textareas, and links. |
| V-006 | Minor | Open | `01_leads.jpg` | `icp_engine/web_assets/app.js` | Low-evidence runs can make Review Flags dominate the detail panel. | Consider grouping hard-gate warnings into a collapsible section or showing the top 3 with a count. |
| V-007 | Minor | Open | Capture plan | Future test stack | Mobile screenshots and browser E2E are not covered because the repo has no Playwright/Cypress/package infrastructure. | Add a dedicated E2E/test stack decision in a later epic before public launch. |
| V-008 | Minor | Fixed | `07_candidate_preview.jpg` | `icp_engine/research.py` | Candidate preview initially showed “No company domains were discovered” even when manual seed candidates were visible, which made the refinement state look contradictory. | Changed the warning to “No additional company domains were discovered from search results” when seed candidates are present and added regression coverage. |
| V-009 | Minor | Fixed | `01_leads.jpg` | `icp_engine/web_assets/app.js` | Active criteria were applied by the pipeline but initially had no visible lead-detail confirmation. | Added an Active Criteria section showing hash, thresholds, budget range, and priority terms; recapture shows it fits in the detail panel. |
| V-010 | Minor | Fixed | `03_research.jpg` | `icp_engine/research.py`, `icp_engine/web_assets/app.js`, `icp_engine/web_assets/styles.css` | Local research answers were terse and visually collapsed into one paragraph, underusing available metadata. | Added structured GTM briefs, metadata-used chips, matched leads, source-aware citation tags, and preserved multiline formatting; recapture shows the result is readable. |

## UX Rationale

- The lead and prospect tables need to support finding, comparing, drilling into, and acting on records. NN/g frames these as the common core tasks for useful data tables, which matches this GTM workflow.
- Focus visibility is a WCAG 2.2 AA expectation for keyboard-operable interfaces. The added `:focus-visible` rule gives operators a clear focus indicator across controls.
- The dashboard definition as an at-a-glance single-page tool supports the current direction: top KPIs, dense tables, and detail panes are appropriate, but repeated warnings should not drown out the primary lead decision.

## Wireframe Notes

- `wireframe_dashboard.jpg`: keep the dense lead-table/detail-panel composition, but preserve readable strategy wrapping and clear keyboard focus.
- `wireframe_prospects.jpg`: keep the compact summary metrics and export actions, with human-readable contact/status labels.
- `wireframe_k2.jpg`: keep K2 metadata as an operator surface, but visually separate safe preview/export actions from live apply sync.
- `wireframe_research_criteria.jpg`: keep form-first layouts for natural-language research and criteria editing, with clear answer/citation regions.
- `07_candidate_preview.jpg` verifies the implemented refinement flow: preview candidates, select/deselect rows, and then run only chosen accounts. No new wireframe was generated for this incremental fixed state.
- `01_leads.jpg` also verifies the Active Criteria detail block after the criteria-profile scoring update. No new wireframe was generated for this incremental fixed state.
- `03_research.jpg` verifies the structured local GTM research brief, metadata-used tags, matched lead chips, and source-aware citations. No new wireframe was generated for this incremental fixed state.

## Action Items

| ID | Priority | Work Item | Acceptance Criteria |
|----|----------|-----------|---------------------|
| UX-001 | P2 | Collapse or summarize repeated Review Flags in lead detail. | Low-evidence seeded runs show hard gates clearly without pushing the evidence section far below the fold. |
| UX-002 | P2 | Add browser E2E/visual coverage for desktop and mobile tabs. | A repeatable command captures Leads, Prospects, Research, K2, and Criteria on desktop and mobile. |
| UX-003 | P3 | Add richer empty states after auth/provider failures. | 401/provider-missing states include a clear next action without exposing secrets or raw stack traces. |

## References

- W3C WCAG 2.2 Focus Visible and Focus Not Obscured criteria: https://www.w3.org/TR/WCAG22/
- W3C Understanding Focus Appearance: https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html
- NN/g Data Tables: Four Major User Tasks: https://www.nngroup.com/articles/data-tables/
- NN/g Dashboards and at-a-glance information: https://www.nngroup.com/articles/dashboards-preattentive/
