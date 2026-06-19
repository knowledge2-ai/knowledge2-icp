# Cloud Run deployment runbook

The hosted dashboard (`icp_engine` Python + bundled React SPA) runs as a single
container on Cloud Run. The image is pure stdlib — no pip install, no build step
beyond `COPY icp_engine/`. This runbook is the cutover from the Cloudflare
`worker.js` reimplementation to the real Python engine.

## Prerequisites (operator-supplied)

- `gcloud` authenticated against the target GCP project (`gcloud auth login`).
- A project id and region (e.g. `us-central1`).
- The K2 + admin secrets stored in Secret Manager (never baked into the image):
  `ICP_ADMIN_TOKEN`, `K2_API_KEY`, and the `K2_*_CORPUS_ID` set.

## Image contract (verified locally)

`docker build -t icp-engine .` then `docker run -p 8080:8080 -e ICP_ADMIN_TOKEN=… icp-engine`:

- Serves the SPA at `/` (200, no token).
- Gates every `/api/*` route — 401 without a bearer token, served with it.
- Binding `0.0.0.0` forces `ICP_ADMIN_TOKEN` (web.py refuses a non-loopback bind
  without it), so the demo is never open.
- State persists under `--state-dir` (`/data`), mounted as a durable volume.

## Deploy

```sh
PROJECT=<gcp-project-id>
REGION=us-central1

# 1. Build + push via Cloud Build (respects .gcloudignore — secrets/tools excluded).
gcloud builds submit --tag gcr.io/$PROJECT/icp-engine --project $PROJECT

# 2. Deploy, wiring secrets from Secret Manager (not plaintext env).
gcloud run deploy icp-engine \
  --image gcr.io/$PROJECT/icp-engine \
  --project $PROJECT --region $REGION \
  --allow-unauthenticated \
  --port 8080 \
  --set-secrets ICP_ADMIN_TOKEN=icp-admin-token:latest,K2_API_KEY=k2-api-key:latest \
  --set-env-vars ICP_STATE_DIR=/data

# 3. Confirm the service is live and token-gated.
URL=$(gcloud run services describe icp-engine --region $REGION --project $PROJECT --format='value(status.url)')
curl -s -o /dev/null -w '%{http_code}\n' "$URL/"                      # 200 (SPA)
curl -s -o /dev/null -w '%{http_code}\n' "$URL/api/state"            # 401 (gated)
```

State note: Cloud Run's container filesystem is ephemeral. For durable run state,
mount a GCS volume at `/data` (`--add-volume`/`--add-volume-mount`) or point
`ICP_STATE_DIR` at a persistent backend before relying on it for the demo.

## Cutover (#45) and worker retirement (#46)

1. Point `gtm-dev.knowledge2.ai` at the Cloud Run URL (DNS / Cloudflare CDN origin).
2. Verify the live demo serves from the Python engine (response headers no longer
   show `server: cloudflare` worker version).
3. Once stable, retire `deployment/cloudflare/worker.js` + `wrangler` config — the
   parallel JS reimplementation is the maintenance tax this cutover removes.
