# Síntesis Económica V2

Pipeline ELT de indicadores económicos de la Región de Valparaíso y Chile (INE, Banco Central, Senado),
desplegable en Google Cloud: ingesta en Cloud Run Jobs → Cloud Storage (raw) → BigQuery → dbt,
con infraestructura como código (Terraform) y CI/CD en GitHub Actions.

> **Estado:** en construcción — fase 0 (fundaciones). Ver [docs/plan.md](docs/plan.md).

## Desarrollo local

Requisitos: [uv](https://docs.astral.sh/uv/) y `make` (en WSL/Linux).

```bash
make setup   # instala dependencias y los hooks de pre-commit
make test    # corre los tests
make lint    # corre ruff, detect-secrets y los demás hooks sobre todo el repo
```
