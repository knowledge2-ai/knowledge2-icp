FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ICP_TENANT=knowledge2

# The app is pure stdlib (no pip dependencies) and self-contained in this package,
# so the image only needs the icp_engine tree (web SPA assets live under it).
COPY icp_engine/ /app/icp_engine/

EXPOSE 8080

# Cloud Run injects $PORT (default 8080). State persists under /data, which is a
# durable GCS volume mounted by the Cloud Run service. Binding 0.0.0.0 forces the
# app to require ICP_ADMIN_TOKEN for every /api/* route (token-gated demo).
CMD ["sh", "-c", "exec python -m icp_engine.web --host 0.0.0.0 --port ${PORT:-8080} --state-dir ${ICP_STATE_DIR:-/data}"]
