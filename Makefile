PYTHON ?= python
PIP ?= $(PYTHON) -m pip
NPM ?= npm

.PHONY: help setup install install-backend install-frontend test test-backend test-frontend \
	lint typecheck check dev run-backend run-frontend \
	evaluate-baseline evaluate-agent compare generate-cases versions docker-up docker-down

help:
	@echo ForecastWize targets:
	@echo   make setup                 .env from example if missing; pip + npm ci
	@echo   make test                  Backend pytest + frontend typecheck
	@echo   make dev                   API :8000 and UI :3000 together
	@echo   make evaluate-baseline     Shared catalog; writes evaluation/results/baseline.json
	@echo   make evaluate-agent        Same cases; writes evaluation/results/agent.json
	@echo   make compare               Writes evaluation/results/comparison.json
	@echo   make check                 Ruff + pytest + frontend typecheck and build
	@echo   make docker-up             docker compose up --build

setup:
	$(PYTHON) scripts/setup.py

install: setup

install-backend:
	$(PIP) install -r backend/requirements.txt

install-frontend:
	cd frontend && $(NPM) ci

test:
	$(PYTHON) scripts/test.py

test-backend:
	cd backend && $(PYTHON) -m pytest

test-frontend:
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) run build

lint:
	cd backend && $(PYTHON) -m ruff check .
	cd backend && $(PYTHON) -m ruff format --check .
	$(PYTHON) -m ruff check --config backend/pyproject.toml evaluation scripts
	$(PYTHON) -m ruff format --check --config backend/pyproject.toml evaluation scripts

typecheck: test

dev:
	$(PYTHON) scripts/dev.py

run-backend:
	cd backend && $(PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

run-frontend:
	cd frontend && $(NPM) run dev

evaluate-baseline:
	$(PYTHON) evaluation/run_baseline.py

evaluate-agent:
	$(PYTHON) evaluation/run_agent.py

compare:
	$(PYTHON) evaluation/compare.py

generate-cases:
	$(PYTHON) -m evaluation.cases.generators

versions:
	$(PYTHON) --version
	node -v
	$(PYTHON) -c "from importlib import metadata; print('pandas', metadata.version('pandas')); print('numpy', metadata.version('numpy')); print('scipy', metadata.version('scipy')); print('statsmodels', metadata.version('statsmodels'))"

check: lint test-backend test-frontend

docker-up:
	docker compose up --build

docker-down:
	docker compose down
