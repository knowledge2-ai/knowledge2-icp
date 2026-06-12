# Epic 002 Plan: Metadata-Heavy Research And K2 Manifest Export

## Scope

Advance the local web app toward the requested K2-backed agentic research product by preserving rich source metadata, making it visible in the dashboard, and adding a K2-ready manifest export endpoint for each research run.

## Source Traceability

- FR-2: Search internet for companies.
- FR-3: Scrape websites, GitHub, LinkedIn, and other public resources for company data.
- FR-9: Natural-language research interface over collected evidence and metadata.
- FR-11: Include a Knowledge2 backend integration path.
- NFR-5: Data records must retain source URLs and metadata for future K2 ingestion and cited generation.

## Tasks

### T-001 Preserve Evidence Metadata

Files:

- `icp_engine/models.py`: add optional `source_type` and `metadata` fields to `Evidence`.
- `icp_engine/enrichment.py`: persist source type, page category, and bounded outbound links from fetched pages.
- `icp_engine/evidence.py`: preserve metadata during dedupe.

Acceptance criteria:

- Existing code that constructs `Evidence(evidence_id, url, title, text)` continues to work.
- Website evidence includes page category and social/contact/doc links when present.

Test command:

```bash
python3 -m unittest tests.test_enrichment tests.test_evidence
```

### T-002 Add Metadata Extraction Layer

Files:

- `icp_engine/metadata.py`: create source classification, link extraction, signal tags, source counts, public social/contact refs, and lead-level metadata summary helpers.
- `tests/test_metadata.py`: cover source classification and lead metadata summaries.

Acceptance criteria:

- LinkedIn, GitHub, docs, pricing, careers, case-study, and contact refs are classified deterministically.
- Evidence-level tags and lead-level source counts can be serialized to JSON.

Test command:

```bash
python3 -m unittest tests.test_metadata
```

### T-003 Wire Metadata Into Runs And Local Research

Files:

- `icp_engine/research.py`: merge extracted metadata with candidate/GitHub/Apollo metadata and include metadata snippets in local question answering.
- `tests/test_research.py`: assert metadata summary and source refs appear on stored leads and can be cited.

Acceptance criteria:

- Each lead stores source counts, source refs, evidence metadata, and K2 metadata preview.
- Local natural-language research can match source metadata, not just raw evidence text.

Test command:

```bash
python3 -m unittest tests.test_research
```

### T-004 Add K2 Manifest Export API

Files:

- `icp_engine/k2_backend.py`: include account-summary documents and richer metadata fields.
- `icp_engine/web.py`: add `GET /api/runs/{run_id}/k2-manifest` and `POST /api/runs/{run_id}/k2-export`.
- `tests/test_web.py`: cover manifest and export endpoints.

Acceptance criteria:

- Manifest endpoint returns documents without writing files.
- Export endpoint writes a JSON manifest under app state and returns the path.
- Manifest documents include metadata keys needed for K2 filtering.

Test command:

```bash
python3 -m unittest tests.test_web
```

### T-005 Expose Metadata In Dashboard

Files:

- `icp_engine/web_assets/index.html`: add a K2/metadata view.
- `icp_engine/web_assets/app.js`: render source counts, refs, K2 manifest preview, and export controls.
- `icp_engine/web_assets/styles.css`: add compact metadata panels.

Acceptance criteria:

- Lead detail shows source metadata counts and public refs.
- K2 view shows manifest document count and allows export for current run.

Test command:

```bash
python3 -m unittest discover -s tests
```

### T-006 Documentation And Verification

Files:

- `docs/CLOUDFLARE_K2_DEPLOYMENT.md`: document K2 manifest export contract.
- `docs/OPERATIONS.md`: document the new API endpoints.
- `docs/agentic-gtm-dashboard/state.md`: update Epic 2 status and decisions log.

Acceptance criteria:

- Full test suite passes.
- `python3 -m py_compile icp_engine/*.py` passes.
- Local API smoke confirms K2 manifest endpoint works.

Test command:

```bash
python3 -m py_compile icp_engine/*.py
python3 -m unittest discover -s tests
```
