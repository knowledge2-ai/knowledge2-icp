# UI Review Plan

## Application Overview

The Agentic GTM dashboard is a local-first operations console for GTM operators, admin/operators, and sales researchers. It uses a Python standard-library HTTP server, static HTML/CSS/JS assets, JSON APIs, and local JSON state under `out/app_state`.

## Authentication Strategy

For screenshot capture, run the dashboard in local open mode with `ICP_ADMIN_TOKEN` unset. Epic 5 adds optional bearer-token protection for production and protected local operation, but screenshots should exercise the default local setup documented for deterministic review.

## Data Seeding Strategy

The scenario file creates a deterministic no-fetch run through `POST /api/runs` before capture. The run uses one seeded company and disables external providers so screenshots are populated without network credentials.

## Route Inventory

| # | Route Pattern | Page Component | Dynamic Segments | Requires Data |
|---|---------------|----------------|------------------|---------------|
| 1 | `/` | Static dashboard shell from `icp_engine/web_assets/index.html` | none | latest run preferred |
| 2 | `/api/state` | JSON state endpoint used by dashboard | none | no |
| 3 | `/api/runs/{run_id}` | JSON run detail endpoint | `run_id` | yes |
| 4 | `/api/runs/{run_id}/prospects` | JSON prospects endpoint | `run_id` | yes |
| 5 | `/api/runs/{run_id}/k2-manifest` | JSON K2 manifest endpoint | `run_id` | yes |

## Scenario Design

The capture flow starts at `/`, waits for seeded lead rows, and navigates through each primary dashboard tab. The K2 scenario also clicks `Preview manifest` because the manifest preview is an important metadata-heavy state.

## Variables

| Variable | Source | Used By |
|----------|--------|---------|
| `run_id` | Seed command stdout | debugging/reference only |

## Capture Checklist

- [x] Leads view with populated run
- [x] Prospects/persona view
- [x] Natural-language research view
- [x] K2 view default state
- [x] K2 manifest preview state
- [x] Criteria admin editor
- [ ] Mobile viewport: deferred; capture utility scenario schema has no per-step viewport action, and desktop coverage is the launch-critical GTM operator layout

## In-Page States Inventory

| Route | Trigger | State Name | Screenshot Scenario |
|-------|---------|------------|---------------------|
| `/` | default load | Leads table and selected lead detail | `01_dashboard_tabs`, step 3 |
| `/` | click `Prospects` tab | Prospect/persona export table | `01_dashboard_tabs`, step 6 |
| `/` | click `Research` tab | Natural-language research form | `01_dashboard_tabs`, step 8 |
| `/` | click `K2` tab | K2 status panel | `01_dashboard_tabs`, step 10 |
| `/` | click `Preview manifest` | K2 manifest preview | `01_dashboard_tabs`, step 13 |
| `/` | click `Criteria` tab | Criteria editor | `01_dashboard_tabs`, step 15 |
