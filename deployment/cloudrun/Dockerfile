# Cloud Run image for the Python GTM engine (icp_engine.web).
#
# The engine is pure stdlib — pyproject `dependencies = []`, every import is
# stdlib (only `ssl`, also stdlib). So there is no pip install step and no
# requirements.txt: we copy the package and run it. The seeded demo run
# (run-seeded-icp, 424 leads) is code-resident in icp_engine/seed_defaults.py
# + icp_engine/tenants/knowledge2/, so it survives Cloud Run's ephemeral
# filesystem with no persistent disk.
FROM python:3.13-slim

# Don't buffer stdout/stderr — we want logs to reach Cloud Logging promptly.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # State is ephemeral on Cloud Run; the demo run is code-resident, so a
    # tmp dir is enough. User-created runs do not persist across restarts.
    ICP_APP_STATE_DIR=/tmp/app_state

WORKDIR /app

# Copy only the engine package (it bundles web_assets/ and tenants/). The
# .dockerignore keeps tests, out/, node_modules, and the worker out of the image.
COPY icp_engine/ ./icp_engine/

# Run as a non-root user (Cloud Run does not require it, but it's good hygiene).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /tmp/app_state \
    && chown -R appuser /tmp/app_state
USER appuser

# Cloud Run injects PORT (default 8080). Shell-form CMD so ${PORT} expands.
# Host 0.0.0.0 is required to accept Cloud Run traffic; run_server() refuses a
# non-loopback bind unless an admin token is set OR ICP_ALLOW_OPEN_API is true
# OR (pending) a read-only demo mode is enabled — see deploy.sh / README.
CMD python3 -m icp_engine.web --host 0.0.0.0 --port ${PORT:-8080}
