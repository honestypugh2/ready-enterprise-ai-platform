# ---------------------------------------------------------------------------
# ready-enterprise-ai-platform
#
# `make help` lists everything. Every target below runs against local mock mode
# by default and needs no Azure subscription, credential or network access.
#
# uv owns the environment. Nothing here calls pip directly, and no target
# installs into a system interpreter.
# ---------------------------------------------------------------------------

SHELL := /bin/bash
.DEFAULT_GOAL := help
.ONESHELL:

UV ?= uv
PY := $(UV) run
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
WEB_DIR := apps/web
DECK_DIR := presentation
SCENARIO ?= major-defect
REPORT ?= reports/evaluation-report.json

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# --- environment -----------------------------------------------------------

.PHONY: install
install: ## Create the venv and install runtime + dev dependencies
	$(UV) venv --python 3.12 .venv
	$(UV) sync --extra dev
	@echo "Activate with: source .venv/bin/activate"

.PHONY: install-all
install-all: ## Install every extra (azure, aml, onnx, dev) to prove they co-resolve
	$(UV) sync --extra dev --extra onnx --extra azure --extra aml

.PHONY: lock
lock: ## Refresh uv.lock against the current constraints
	$(UV) lock --upgrade


.PHONY: lint
lint: ## Lint without modifying files
	$(PY) ruff format --check packages apps tests scripts
	$(PY) ruff check packages apps tests scripts

.PHONY: typecheck
typecheck: ## Static types, strict
	$(PY) mypy packages apps

.PHONY: test
test: ## Unit, contract and security suites (deterministic, offline)
	$(PY) pytest tests/unit tests/contract tests/security -q

.PHONY: test-all
test-all: ## Every suite except integration and load
	$(PY) pytest tests -q --ignore=tests/integration --ignore=tests/load

.PHONY: test-integration
test-integration: ## Integration suite; requires live Azure dependencies
	REAP_RUN_INTEGRATION=1 $(PY) pytest tests/integration -q

.PHONY: coverage
coverage: ## Test suites with a coverage report
	$(PY) pytest tests/unit tests/contract tests/security \
	  --cov=packages --cov=apps --cov-report=term-missing --cov-report=xml

# --- evaluation and readiness ---------------------------------------------

.PHONY: eval
eval: ## Run the evaluation release gate (non-zero exit blocks a release)
	@mkdir -p $(dir $(REPORT))
	$(PY) reap eval --report $(REPORT)

.PHONY: ready
ready: ## Score the reference workload with READY AI
	$(PY) reap ready

.PHONY: doctor
doctor: ## Check configuration, plane health and governance artifacts
	$(PY) reap doctor

# --- demo ------------------------------------------------------------------

.PHONY: demo
demo: ## Run the governed demo (SCENARIO=critical-defect to change it)
	$(PY) reap demo run --scenario $(SCENARIO)

.PHONY: demo-list
demo-list: ## List available demo scenarios
	$(PY) reap demo list

.PHONY: demo-all
demo-all: ## Run every scenario, to prove policy behaviour across the matrix
	@for s in $$($(PY) reap demo list | awk 'NR>4 && NF {print $$1}'); do \
	  echo "=== $$s ==="; \
	  $(PY) reap demo run --scenario $$s > /dev/null && echo "  ok" || echo "  FAILED"; \
	done

.PHONY: azure-demo-index
azure-demo-index: ## Upload synthetic fixtures to Azure AI Search (requires azure_dev)
	$(PY) reap azure index

.PHONY: azure-demo-preflight
azure-demo-preflight: ## Verify live Azure demo prerequisites (requires azure_dev)
	$(PY) reap azure preflight

.PHONY: azure-demo-infra-preview
azure-demo-infra-preview: ## Preview the Search-only conference demo infrastructure
	az deployment group what-if --resource-group $${DEMO_RESOURCE_GROUP:-rg-replen-demo} --name reap-demo-search --template-file infra/demo/main.bicep --parameters infra/demo/dev.bicepparam

.PHONY: azure-demo-infra-deploy
azure-demo-infra-deploy: ## Deploy the Search-only conference demo infrastructure
	az deployment group create --resource-group $${DEMO_RESOURCE_GROUP:-rg-replen-demo} --name reap-demo-search --template-file infra/demo/main.bicep --parameters infra/demo/dev.bicepparam

# --- run -------------------------------------------------------------------

.PHONY: dev
dev: ## Start the API with reload on http://$(API_HOST):$(API_PORT)/docs
	$(PY) uvicorn api.main:app --reload --host $(API_HOST) --port $(API_PORT)

.PHONY: worker
worker: ## Start the event worker
	$(PY) python -m worker.main

.PHONY: web
web: ## Start the demo UI on http://localhost:5173
	cd $(WEB_DIR) && npm install && npm run dev

.PHONY: web-build
web-build: ## Type-check, lint, test and build the frontend
	cd $(WEB_DIR) && npm install && npm run lint && npm run typecheck && npm run test && npm run build

.PHONY: deck
deck: ## Present the session deck on http://localhost:5180 (press S for speaker notes)
	cd $(DECK_DIR) && npm install && npm run dev

.PHONY: deck-build
deck-build: ## Build the deck to presentation/dist, presentable from disk with no server
	cd $(DECK_DIR) && npm install && npm run build

.PHONY: deck-check
deck-check: ## Build the deck and prove every slide fits conference and laptop viewports
	cd $(DECK_DIR) && npm ci && npm run build && npm run test:layout

.PHONY: up
up: ## Start API + worker + web with docker compose
	docker compose up --build

.PHONY: down
down: ## Stop the compose stack
	docker compose down -v

# --- security --------------------------------------------------------------

.PHONY: security
security: ## Dependency audit, static analysis and secret scan
	$(PY) pip-audit --skip-editable --strict
	$(PY) bandit -q -c pyproject.toml -r packages apps
	$(MAKE) secrets

.PHONY: secrets
secrets: ## Fail if anything credential-shaped is tracked in git
	@./scripts/scan-secrets.sh

.PHONY: sbom
sbom: ## Generate a CycloneDX SBOM for the installed dependency set
	$(UV) run --with cyclonedx-bom cyclonedx-py environment .venv -o sbom.json
	@echo "wrote sbom.json"

# --- infrastructure --------------------------------------------------------

.PHONY: infra-lint
infra-lint: ## Build and lint every Bicep template
	@./scripts/validate-bicep.sh

.PHONY: infra-whatif
infra-whatif: ## Preview changes against a subscription (requires az login)
	@./scripts/deploy.sh --what-if

# --- aggregate -------------------------------------------------------------

.PHONY: check
check: lint typecheck test ## What CI runs on a pull request

.PHONY: gate
gate: check eval ## What must pass before a release is proposed
	@echo "release gate complete — see $(REPORT)"
