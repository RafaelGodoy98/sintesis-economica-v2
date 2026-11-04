.DEFAULT_GOAL := help
.PHONY: help setup test lint run-local

help: ## Lista los comandos disponibles
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

setup: ## Instala dependencias (uv) y los hooks de pre-commit
	uv sync
	uv run pre-commit install

test: ## Corre los tests
	uv run pytest

lint: ## Corre todos los hooks de pre-commit sobre el repo
	uv run pre-commit run --all-files

run-local: ## Corre una fuente en local: make run-local SOURCE=bcentral_uf (datos en ./data)
	@test -n "$(SOURCE)" || (echo "Falta SOURCE. Ej.: make run-local SOURCE=bcentral_uf"; exit 2)
	uv run sintesis-ingest run --source $(SOURCE)
