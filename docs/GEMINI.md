# Gemini / Vertex AI Setup

The CLI can run fully rules-only. Gemini is optional and used only to classify
public evidence snippets.

## Default Runtime

The default model configuration is:

```bash
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-3.5-flash
GEMINI_THINKING_BUDGET=0
```

`GEMINI_THINKING_BUDGET=0` requests minimal thinking/low-latency behavior.

## Service Account

For the `k2-demo-483116` project, the current local development service account is:

```text
codex-icp-engine@k2-demo-483116.iam.gserviceaccount.com
```

It has:

- `roles/aiplatform.user`
- `roles/serviceusage.serviceUsageConsumer`

The JSON key must stay outside git. This repo ignores `.secrets/`.

## Local Run

```bash
cp .env.example .env
# Update GOOGLE_APPLICATION_CREDENTIALS if needed.
set -a
. ./.env
set +a
.venv/bin/python -m icp_engine.cli qualify \
  --input examples/companies.csv \
  --out out/gemini \
  --use-gemini
```
