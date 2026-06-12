.PHONY: setup test smoke smoke-gemini clean

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[gemini,dev]'

test:
	python3 -m unittest discover -s tests

smoke:
	python3 -m icp_engine.cli qualify --input examples/companies.csv --out out/smoke --no-fetch

smoke-gemini:
	. ./.env.example && .venv/bin/python -m icp_engine.cli qualify --input examples/companies.csv --out out/smoke-gemini --use-gemini --max-pages 1 --timeout 5

clean:
	rm -rf out .pytest_cache icp_engine/__pycache__ tests/__pycache__
