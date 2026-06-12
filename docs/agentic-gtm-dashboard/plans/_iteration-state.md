# Iteration State: agentic-gtm-dashboard

## Delivered

| Epic | Title | Status | Evidence |
| ---- | ----- | ------ | -------- |
| 001 | Runnable Local Agentic GTM Dashboard | delivered | Web/API app, local persistence, provider seams, tests passing |
| 002 | Metadata-Heavy Research And K2 Manifest Export | delivered | Evidence metadata, dashboard K2 tab, manifest preview/export API, tests passing |
| 003 | Live K2 Sync And Cloudflare Deploy Shell | delivered | K2 REST sync client/CLI/API, Worker asset/proxy shell, Wrangler dry-run passing |
| 004 | Apollo Prospect Enrichment And Export | delivered | Prospect normalization, persona fallback, dashboard tab, CSV/JSON export, K2 prospect documents |
| 005 | Production Hardening And Deployment Guardrails | delivered | Optional API bearer auth, Cloudflare edge guard, UX screenshots/wireframes, tests and Wrangler dry-run passing |
| 006 | Deployment Readiness And Completion Audit | delivered | Origin/edge health probes, readiness docs, requirement audit, tests and Wrangler dry-run passing |
| 007 | Public Source Intelligence Hardening | delivered | Search-result profile/resource association, typed source refs, dashboard coverage flags, K2 source-reference metadata, tests passing |
| 008 | Candidate Preview And Search Refinement | delivered | `/api/search` preview workflow, checkbox candidate selection, selected-candidate run payloads, tests passing |
| 009 | Active Criteria Scoring Profile | delivered | Criteria markdown parser, threshold/range/priority-term scoring influence, lead/K2 criteria metadata, rendered UI evidence, tests passing |
| 010 | Public Resource Evidence Collection | delivered | Candidate GitHub/marketplace/social refs feed the evidence queue, LinkedIn refs remain metadata-only, source classifications and tests passing |
| 011 | Metadata-Backed Research Briefs | delivered | Local research fallback returns structured GTM briefs, metadata-used tags, matched leads, source-aware citations, rendered Research screenshot, tests passing |
| 012 | Browser E2E Smoke Validation | delivered | Manifest-driven Python Playwright runner starts isolated server, seeds evidence, validates dashboard UI/API/console, `make e2e-smoke` passing |
| 013 | Sanitized Deploy Preflight | delivered | Cloudflare/K2/Apollo preflight checks required env, token presence, generated config shape, no secret printing, tests passing |

## Current Epic

| Epic | Title | Status | Scope |
| ---- | ----- | ------ | ----- |
| 014 | PR And Live Deployment Decision | pending | Commit/PR prep, live Cloudflare/K2 deploy decision, production subdomain/API origin values |

## Backlog

| ID | Title | Tentative Epic |
| -- | ----- | -------------- |
| B-003 | Cloudflare Worker/Pages production target with D1/R2/Queues | 003 |
| B-004 | Live K2 SDK ingestion and generated answers | 003 |
| B-007 | Expanded browser E2E for mobile/auth/failure states | 014 |
| B-008 | Commit and PR preparation | 014 |
| B-009 | Live Cloudflare/K2 deployment after operator confirmation | 014 |

## Open Questions

- Production K2 corpus/project naming should be confirmed before live ingestion.
- Cloudflare subdomain should be selected before creating DNS/routes.
- Browser E2E smoke exists; broader mobile/auth/failure-state coverage remains a CI scope decision.
- Production deploy still needs confirmed subdomain, API origin, and permission to use live Cloudflare/K2 secrets.
