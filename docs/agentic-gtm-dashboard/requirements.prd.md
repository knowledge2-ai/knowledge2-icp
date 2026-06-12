# Agentic GTM Dashboard PRD

## Goal

Turn the current Knowledge2 ICP qualification CLI into a web application for discovering, researching, scoring, and inspecting GTM leads with configurable ICP criteria and a path to Cloudflare, Knowledge2, and Apollo integration.

## Stakeholders

- GTM operator: runs searches, reviews ranked accounts, refines strategy.
- Admin/operator: edits ICP criteria and controls external enrichment providers.
- Sales/research user: inspects company evidence, target personas, metadata, and recommended outreach motions.
- Platform operator: deploys the app and manages secrets for Cloudflare, K2, Apollo, and model providers.

## Functional Requirements

- FR-1: Provide a web dashboard as the primary interface, not only a CLI.
- FR-2: Let users search the internet for companies by natural language query and seed company/domain candidates.
- FR-3: Scrape public company websites for ICP evidence using the existing enrichment/scoring engine.
- FR-4: Collect and display source metadata from websites, GitHub, LinkedIn URLs found in search results, and other public references where available.
- FR-5: Qualify companies against the existing `icp.md` criteria and scoring logic.
- FR-6: Provide an admin UI to view and edit the active ICP criteria markdown/prompt.
- FR-7: Produce ranked leads with score, tier, hard gates, warnings, evidence, strategy, and recommended target personas.
- FR-8: Provide result inspection and filtering by tier, score, warnings, company, domain, vertical, and search run.
- FR-9: Provide a natural language research interface that answers questions over collected company evidence and metadata.
- FR-10: Include an Apollo integration path for company enrichment and prospect/persona discovery.
- FR-11: Include a Knowledge2 backend integration path for storing/querying enriched evidence with metadata.
- FR-12: Include a Cloudflare deployment plan and configuration surface suitable for a K2 subdomain.
- FR-13: Avoid committing secrets; all API keys and tokens must be provided via environment variables or Cloudflare secrets.

## Non-Functional Requirements

- NFR-1: The first slice must run locally with only Python standard-library web dependencies, preserving the lightweight current repo.
- NFR-2: External enrichers must be optional and degrade gracefully when keys are absent.
- NFR-3: Public scraping must use timeouts, cache fetched pages, and surface warnings instead of failing whole runs.
- NFR-4: The UI must be dense, operational, and polished for repeated GTM workflow use.
- NFR-5: Data records must retain source URLs and metadata so future K2 ingestion and cited generation can be reliable.
- NFR-6: Tests must cover scoring reuse, persistence, provider fallbacks, and web API behavior.

## First Epic Acceptance Criteria

- [ ] `python3 -m icp_engine.web` starts a local web dashboard.
- [ ] The dashboard can create a research run from query text and/or seed companies.
- [ ] A run stores ranked leads with evidence, scores, strategy, personas, and warnings.
- [ ] The dashboard can edit and persist ICP markdown without overwriting the canonical `icp.md` unless explicitly requested later.
- [ ] The API exposes state, runs, criteria, search, and research endpoints.
- [ ] Apollo and K2 are represented as explicit optional adapters with environment-variable configuration and no committed secrets.
- [ ] Unit tests pass with no external API credentials.

## Out Of Scope For First Epic

- Auth, team accounts, and multi-tenant authorization.
- Production-grade distributed job queue.
- Direct authenticated LinkedIn scraping.
- Full K2 corpus creation/index build until API surface and deployment target are finalized.
- Sending outbound email or creating CRM tasks.
