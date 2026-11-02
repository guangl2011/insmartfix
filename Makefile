# InsmartFix developer entry points (TEST_PLAN §3). Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE  := docker compose -f infra/docker-compose.yml
API_DIR  := apps/api
UV       := uv --directory $(API_DIR)
ENV      ?= local

.PHONY: help install dev up down seed test test-api test-web test-mobile test-packages \
        e2e-web e2e-android e2e-ios contracts lint build dev-mock clean

help: ## List targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install JS (pnpm) and Python (uv) dependencies
	pnpm install --frozen-lockfile
	$(UV) sync --frozen

dev: ## Web dev server (DATA_SOURCE=live) against the API on :8000 — run `make up` or the API first
	pnpm dev

infra/.env:
	cp infra/.env.example infra/.env

up: infra/.env ## local-stack: build and start postgres, minio, api, web, toxiproxy (waits until healthy)
	$(COMPOSE) up -d --build --wait

down: ## Stop the local stack and delete its volumes
	$(COMPOSE) down -v --remove-orphans

seed: infra/.env ## Load TEST_PLAN §5 fixtures (ENV=local|staging); needs SEED_PASSWORD in the env
	@test -n "$$SEED_PASSWORD" || { echo "seed: set SEED_PASSWORD (test-account password, never committed)"; exit 1; }
ifeq ($(ENV),local)
	$(COMPOSE) exec -T -e SEED_PASSWORD api python -m app.seed
else
	@test -n "$$DATABASE_URL" || { echo "seed: set DATABASE_URL for ENV=$(ENV)"; exit 1; }
	$(UV) run python -m app.seed
endif

test: test-api test-packages test-web test-mobile ## All unit/integration tests with coverage thresholds

test-api: ## API: pytest (+ integration when DATABASE_URL is Postgres) and TEST_PLAN §4 thresholds
	cd $(API_DIR) && uv run pytest --cov --cov-report=term --cov-report=json --cov-report=xml
	cd $(API_DIR) && uv run python scripts/check_coverage.py coverage.json

test-packages: ## Shared packages: contracts, core, tokens, ui-web
	pnpm turbo run test:coverage --filter "./packages/*"

test-web: ## Web: vitest + RTL with coverage
	pnpm turbo run test:coverage --filter @insmartfix/web

test-mobile: ## Mobile: jest + RNTL with coverage
	pnpm turbo run test:coverage --filter @insmartfix/mobile

e2e-web: ## Playwright (Pixel 7, iPhone 14, desktop). Against the stack if E2E_BASE_URL is set.
	pnpm --filter @insmartfix/web exec playwright test

e2e-android: ## Maestro flows on a running Android emulator with the app installed
	maestro test apps/mobile/e2e

e2e-ios: ## Maestro flows on a booted iOS simulator with the app installed
	maestro test apps/mobile/e2e

contracts: ## Export openapi.json from the API and regenerate TS types
	pnpm --filter @insmartfix/contracts run generate

lint: ## ruff + mypy (API), eslint + tsc + prettier (JS)
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check . && uv run mypy
	pnpm turbo run lint typecheck
	pnpm exec prettier --check .

build: ## Build web, bundle mobile JS, and build both Docker images
	pnpm turbo run build
	$(COMPOSE) build api web

dev-mock: ## local-mock: web on :3000 with DATA_SOURCE=mock (no backend)
	pnpm dev:mock

clean: ## Remove build output and caches inside the repo
	rm -rf .turbo apps/*/.turbo packages/*/.turbo apps/web/.next apps/mobile/dist \
	  apps/*/coverage packages/*/coverage $(API_DIR)/.pytest_cache $(API_DIR)/coverage.*
