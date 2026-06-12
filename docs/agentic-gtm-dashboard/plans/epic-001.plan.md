# Epic 001 Plan: Runnable Local Agentic GTM Dashboard

## Scope

Build the first end-to-end local web slice that reuses the current ICP engine and establishes provider seams for internet discovery, Apollo, K2, and Cloudflare deployment.

## Tasks

1. Add JSON serialization and persistence for criteria, runs, leads, evidence, and provider metadata.
2. Add discovery provider functions for query-to-company candidate extraction from public search results.
3. Add Apollo and K2 adapter modules that are optional and environment-configured.
4. Add a research pipeline that runs discovery, website evidence fetch, scoring, strategy/persona generation, and persistence.
5. Add a standard-library web server with JSON endpoints and static dashboard assets.
6. Add dashboard UI for search, ranked leads, lead details, criteria editing, and local natural-language research.
7. Update docs and environment examples without committing secrets.
8. Add focused tests for the new behavior and run the full test suite.

## Non-Goals

- Production auth and multi-user roles.
- Full Cloudflare Worker rewrite.
- Authenticated LinkedIn scraping.
- Live K2 corpus mutation in tests.
