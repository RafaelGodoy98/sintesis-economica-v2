.DEFAULT_GOAL := help
.PHONY: help setup test test-docker lint run-local docker-build docker-run

help: ## Lista los comandos disponibles
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

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

docker-build: ## Construye la imagen de ingesta (sintesis-ingest:local)
	docker compose build

DATA_DIR ?= ./data

docker-run: ## Corre una fuente en Docker: make docker-run SOURCE=bcentral_uf [DATA_DIR=./data]
	@test -n "$(SOURCE)" || (echo "Falta SOURCE. Ej.: make docker-run SOURCE=bcentral_uf"; exit 2)
	@mkdir -p $(DATA_DIR)  # si no existe, Docker la crearía a nombre de root
	UID=$$(id -u) GID=$$(id -g) DATA_DIR=$(DATA_DIR) docker compose run --rm ingest run --source $(SOURCE)
