.PHONY: help install test-unit test-integration test-contract test-scenario test-all lint clean

help:
	@echo "vfobs targets:"
	@echo "  install            install service + dev deps (editable)"
	@echo "  test-unit          run unit tests (fast, default)"
	@echo "  test-integration   run integration tests (real Postgres + HTTP)"
	@echo "  test-contract      run contract tests (SDK ↔ API + schema)"
	@echo "  test-scenario      run scenario tests (kind cluster)"
	@echo "  test-all           run the whole pyramid"
	@echo "  lint               ruff check"

install:
	pip install -e '.[dev]'
	pip install -e './vfobs-sdk-python[dev]'

test-unit:
	pytest -m unit

test-integration:
	pytest -m integration

test-contract:
	pytest -m contract

test-scenario:
	pytest -m scenario

test-all:
	pytest -m "unit or integration or contract or scenario"

lint:
	ruff check src tests vfobs-sdk-python

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name '*.egg-info' -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
