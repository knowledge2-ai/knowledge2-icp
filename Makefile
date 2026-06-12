.PHONY: setup test web smoke smoke-gemini e2e-smoke k2-sync-dry-run cloudflare-preflight cloudflare-config cloudflare-dry-run clean

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

k2-sync-dry-run:
	python3 -m icp_engine.k2_sync --run-id $${RUN_ID:?set RUN_ID} --state-dir out/app_state

cloudflare-preflight:
	python3 deployment/cloudflare/preflight.py

cloudflare-config:
	python3 deployment/cloudflare/render_wrangler_config.py

cloudflare-dry-run: cloudflare-config
	wrangler deploy --dry-run --config deployment/cloudflare/wrangler.generated.toml

clean:
	rm -rf out .pytest_cache icp_engine/__pycache__ tests/__pycache__
