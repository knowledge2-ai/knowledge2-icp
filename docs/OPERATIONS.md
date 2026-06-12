# Operations

## Install

```bash
make setup
```

## Run Rules-Only

```bash
python3 -m icp_engine.cli qualify \
  --input examples/companies.csv \
  --out out/rules \
  --no-fetch
```

## Run With Domain Enrichment

```bash
python3 -m icp_engine.cli qualify \
  --input examples/companies.csv \
  --out out/enriched
```

For broad crawls, cap both pages and attempts so one blocked domain cannot stall
the batch:

```bash
python3 -m icp_engine.cli qualify \
  --input companies.csv \
  --out out/broad \
  --max-pages 6 \
  --max-attempts 12 \
  --max-failures 6 \
  --timeout 4
```

## Run With Gemini

```bash
set -a
. ./.env
set +a
.venv/bin/python -m icp_engine.cli qualify \
  --input examples/companies.csv \
  --out out/gemini \
  --use-gemini
```

## Outputs

- `ranked_companies.csv`: sortable qualification table
- `dossier.md`: human-readable company dossiers
- `cache/`: fetched public page snippets used for repeatable scoring

## Security Notes

- Never commit `.secrets/`, `.env`, or generated output under `out/`.
- Service-account keys should be rotated if shared beyond the local operator.
- Prefer a short-lived key or workload identity when moving this into automation.
