# Síntesis Económica V2

Pipeline ELT de indicadores económicos de la Región de Valparaíso y Chile (INE, Banco Central, Senado),
desplegable en Google Cloud: ingesta en Cloud Run Jobs → Cloud Storage (raw) → BigQuery → Dataform,
con infraestructura como código (Terraform) y CI/CD en GitHub Actions.

> **Estado:** en construcción — fase 1 (ingesta del Banco Central). Ver [docs/plan.md](docs/plan.md).

## Desarrollo local

Requisitos: [uv](https://docs.astral.sh/uv/) y `make` (en WSL/Linux).

```bash
make setup   # instala dependencias y los hooks de pre-commit
make test    # corre los tests
make lint    # corre ruff, detect-secrets y los demás hooks sobre todo el repo
make run-local SOURCE=bcentral_uf   # corre una fuente: descarga, guarda en raw y escribe las observaciones
```

`run-local` necesita un `.env` (ver `.env.example`) con `SINTESIS_CONTACT_EMAIL` y, para el Banco Central,
`SINTESIS_BDE_USER` y `SINTESIS_BDE_PASSWORD`. Los datos quedan en `./data` (ignorada por git):
- `data/raw/source=<id>/ingest_date=<AAAA-MM-DD>/<sha256>_<nombre>`: lo que entregó la fuente, tal cual y una sola vez.
- `data/observaciones/source=<id>/<sha256>.csv`: `source_id, serie_id, periodo, valor, file_sha256, archivo_uri, ingested_at`.
- `data/ops/ejecuciones.jsonl`: una línea por fuente y corrida (estado, archivos nuevos/existentes, filas, error).

Código de salida: 0 todo bien · 1 alguna fuente falló (las demás siguen) · 2 la corrida no pudo empezar.
