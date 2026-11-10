.DEFAULT_GOAL := help
.PHONY: help setup test test-docker lint run-local load docker-build docker-run transform-setup transform-compile transform

help: ## Lista los comandos disponibles
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-18s %s\n", $$1, $$2}'

setup: ## Instala dependencias (uv) y los hooks de pre-commit
	uv sync
	uv run pre-commit install

test: ## Corre los tests
	uv run pytest

test-docker: ## Construye la imagen y la prueba aislada (sin credenciales ni internet)
	uv run pytest -m docker

lint: ## Corre todos los hooks de pre-commit sobre el repo
	uv run pre-commit run --all-files

run-local: ## Corre una fuente en local: make run-local SOURCE=bcentral_uf (datos en ./data)
	@test -n "$(SOURCE)" || (echo "Falta SOURCE. Ej.: make run-local SOURCE=bcentral_uf"; exit 2)
	uv run sintesis-ingest run --source $(SOURCE)

load: ## Carga data/observations y data/ops a BigQuery (raw.observations, ops.runs; requiere SINTESIS_GCP_PROJECT y ADC)
	uv run sintesis-ingest load

docker-build: ## Construye la imagen de ingesta (sintesis-ingest:local)
	docker compose build

DATA_DIR ?= ./data

docker-run: ## Corre una fuente en Docker: make docker-run SOURCE=bcentral_uf [DATA_DIR=./data]
	@test -n "$(SOURCE)" || (echo "Falta SOURCE. Ej.: make docker-run SOURCE=bcentral_uf"; exit 2)
	@mkdir -p $(DATA_DIR)  # si no existe, Docker la crearía a nombre de root
	UID=$$(id -u) GID=$$(id -g) DATA_DIR=$(DATA_DIR) docker compose run --rm ingest run --source $(SOURCE)

# --- Dataform (transform/) ---
# La CLI es herramienta de desarrollo y CI: en producción corre el servicio administrado de Dataform (ADR-0001).
# Node (versión en .nvmrc) se instala con nvm; si npx no está en el PATH (make, shells no interactivos), se carga nvm.
transform-setup transform-compile transform: SHELL := /bin/bash  # nvm.sh requiere bash (sh es dash en Ubuntu)
NVM_SH = $${NVM_DIR:-$$HOME/.nvm}/nvm.sh
NODE_ENV = if ! command -v npx >/dev/null 2>&1; then . "$(NVM_SH)" && nvm use --silent >/dev/null; fi;

transform-setup: ## Instala la CLI de Dataform fijada en package-lock.json
	@$(NODE_ENV) npm ci

transform-compile: ## Compila el proyecto Dataform (no toca BigQuery)
	@$(NODE_ENV) npx dataform compile transform

transform: ## Ejecuta Dataform contra BigQuery (requiere ADC y transform/.df-credentials.json)
	@$(NODE_ENV) npx dataform run transform
