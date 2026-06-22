.PHONY: setup test web smoke smoke-gemini e2e-smoke e2e-live-auth k2-sync-dry-run cloudflare-proxy-dry-run clean

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[gemini,dev]'

test:
	python3 -m unittest discover -s tests

web:
	python3 -m icp_engine.web --host 127.0.0.1 --port 8765

smoke:
	python3 -m icp_engine.cli qualify --input examples/companies.csv --out out/smoke --no-fetch

smoke-gemini:
	. ./.env.example && .venv/bin/python -m icp_engine.cli qualify --input examples/companies.csv --out out/smoke-gemini --use-gemini --max-pages 1 --timeout 5

e2e-smoke:
	python3 tests/e2e/run_dashboard_smoke.py

e2e-live-auth:
	python3 tests/e2e/run_dashboard_smoke.py --live-base-url $${ICP_E2E_LIVE_BASE_URL:-https://gtm-dev.knowledge2.ai}

k2-sync-dry-run:
	python3 -m icp_engine.k2_sync --run-id $${RUN_ID:?set RUN_ID} --state-dir out/app_state

# gtm-dev.knowledge2.ai is fronted by the Cloudflare proxy in
# deployment/cloudflare-proxy/, which forwards to the private Cloud Run engine.
cloudflare-proxy-dry-run:
	cd deployment/cloudflare-proxy && wrangler deploy --dry-run

clean:
	rm -rf out .pytest_cache icp_engine/__pycache__ tests/__pycache__
