# Epic 004 Plan: Apollo Prospect Enrichment And Export

## Scope

Turn strategy personas and optional Apollo people results into an exportable outreach target list. The dashboard should show named Apollo prospects when available and deterministic persona targets when Apollo is disabled or returns no people.

## Source Traceability

- FR-7: Produce ranked leads with score, evidence, strategy, and recommended target personas.
- FR-10: Include an Apollo integration path for company enrichment and prospect/persona discovery.
- FR-11: Present a dashboard that includes discovered companies and the persona that should be reached out to.
- NFR-13: Avoid committing secrets.

## Tasks

### T-001 Add Prospect Normalization

Files:

- `icp_engine/prospects.py`: derive ranked prospect rows from saved run data, Apollo people, and strategy personas.
- `icp_engine/apollo.py`: preserve useful contact fields from Apollo people responses.
- `tests/test_prospects.py`: cover Apollo people, strategy fallback, and CSV output.

Acceptance criteria:

- Apollo people map to company, title, persona, LinkedIn, email, source, and priority score.
- Runs without Apollo still produce persona target rows.
- CSV output is stable and headered.

Test command:

```bash
python3 -m unittest tests.test_prospects
```

### T-002 Add Prospect API And CSV Export

Files:

- `icp_engine/web.py`: add `GET /api/runs/{run_id}/prospects` and `GET /api/runs/{run_id}/prospects.csv`.
- `tests/test_web.py`: cover both endpoints.

Acceptance criteria:

- JSON endpoint returns prospect count, source counts, and prospect rows.
- CSV endpoint returns a downloadable text/csv response.
- Missing run IDs return 404 JSON errors.

Test command:

```bash
python3 -m unittest tests.test_web
```

### T-003 Surface Prospects In Dashboard And K2 Metadata

Files:

- `icp_engine/web_assets/index.html`: add a Prospects dashboard view.
- `icp_engine/web_assets/app.js`: render prospect rows and export controls.
- `icp_engine/web_assets/styles.css`: add prospect table and summary styling.
- `icp_engine/k2_backend.py`: include prospect/persona documents in K2 manifests.

Acceptance criteria:

- Dashboard shows prospect/persona rows for the current run.
- CSV and JSON export controls are available from the Prospects tab.
- K2 manifests include `source_type=prospect` records for persona/contact retrieval.

Test command:

```bash
python3 -m unittest tests.test_k2_sync tests.test_web
```

### T-004 Documentation And Verification

Files:

- `README.md`: document prospect tab and exports.
- `docs/OPERATIONS.md`: document prospect API checks.
- `docs/CLOUDFLARE_K2_DEPLOYMENT.md`: document Apollo/prospect export contract.
- `docs/agentic-gtm-dashboard/state.md`: update Epic 4 status.

Acceptance criteria:

- `python3 -m py_compile icp_engine/*.py` passes.
- `python3 -m unittest discover -s tests` passes.
- Local server exposes prospects JSON and CSV for a new run.

Test command:

```bash
python3 -m py_compile icp_engine/*.py
python3 -m unittest discover -s tests
```
