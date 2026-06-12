# Knowledge2 ICP Qualification Engine

This repo scores company lists against the incumbent-software ICP in `icp.md`.

It is designed for Knowledge² outbound and design-partner qualification:
mature B2B/B2B2C software companies with proprietary workflow/data assets,
enough scale to feel AI pressure, and limited public AI traction.

## Quick start

```bash
python3 -m icp_engine.cli qualify --input examples/companies.csv --out out
```

Outputs:

- `out/ranked_companies.csv`
- `out/dossier.md`
- `out/cache/` with fetched public pages

## Input CSV

Required:

- `company`
- `domain`

Optional:

- `category`
- `founded_year`
- `employee_count`
- `hq`
- `notes`

## Gemini-assisted scoring

Gemini is optional. Without credentials, the engine uses deterministic rules.

To enable Gemini through Vertex AI:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=global
export GEMINI_MODEL=gemini-3.5-flash
export GEMINI_THINKING_BUDGET=0
python3 -m icp_engine.cli qualify --input companies.csv --out out --use-gemini
```

The model only classifies public evidence snippets. Local scoring validates and
clamps all model output.

This repo defaults to `gemini-3.5-flash` with `GEMINI_THINKING_BUDGET=0` for
minimal thinking/low-latency classification.

## Validate

```bash
python3 -m unittest discover -s tests
python3 -m icp_engine.cli qualify --input examples/companies.csv --out out --no-fetch
```

## Docs

- `docs/SCORING.md`: hard gates, posture rubric, and tiering
- `docs/GEMINI.md`: Vertex AI / Gemini service-account setup
- `docs/OPERATIONS.md`: common local runbooks
