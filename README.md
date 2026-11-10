# Síntesis Económica V2

Pipeline ELT de indicadores económicos de la Región de Valparaíso y Chile (INE, Banco Central, Senado),
desplegable en Google Cloud: ingesta en Cloud Run Jobs → Cloud Storage (raw) → BigQuery → Dataform,
con infraestructura como código (Terraform) y CI/CD en GitHub Actions.

> **Estado:** en construcción — fase 1 cerrada (ingesta del Banco Central, en Docker); en curso la fase 2 (BigQuery +
> Dataform; go/no-go de Dataform con el sandbox: GO). Ver [docs/plan.md](docs/plan.md) y la [guía del código](docs/codigo.md).

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
- `data/observations/source=<id>/<sha256>.csv`: `source_id, series_id, period, value, file_sha256, raw_path, ingest_date`
  (`raw_path` relativa a `data/raw/`; `ingest_date` = fecha del primer guardado del raw).
- `data/ops/runs.jsonl`: una línea por fuente y corrida (`status`, `new_files`, `existing_files`, `rows_written`, `duration_s`, `error`).

Carga a BigQuery (`raw.observations`, `ops.runs` y los CSV de `reference/`, en us-central1): `make load`. Requiere las credenciales de GCP (abajo)
y `SINTESIS_GCP_PROJECT` en el `.env`. Cada carga reemplaza las tablas completas desde estos archivos (`WRITE_TRUNCATE`).

Código de salida: 0 todo bien · 1 alguna fuente falló (las demás siguen) · 2 la corrida no pudo empezar.

### Docker

Requisito: Docker (en Windows, Docker Desktop con la integración de WSL activa).

```bash
make docker-build                    # construye la imagen sintesis-ingest:local (ingest/Dockerfile)
make docker-run SOURCE=bcentral_uf   # corre una fuente en un contenedor; datos en ./data (o DATA_DIR=<carpeta>)
make test-docker                     # prueba la imagen aislada: sin repo, sin credenciales y sin red
```

La imagen no contiene el `.env` ni los tests: las credenciales entran como variables de entorno al correr
(como en Cloud Run) y `./data` se monta en `/app/data`. Corre como usuario sin privilegios.

### Credenciales de GCP (fase 2, prueba gratuita)

La fase 2 usa BigQuery con tu usuario de Google. El login lo hace la persona en su terminal (en Claude Code, con `!`),
nunca el asistente:

```bash
gcloud auth login                                      # credencial de gcloud y bq
gcloud config set project <ID_DEL_PROYECTO>
gcloud auth application-default login                  # credencial ADC: la usan las librerías (Python, Dataform)
gcloud auth application-default set-quota-project <ID_DEL_PROYECTO>   # solo si el login no lo dejó configurado
```

Ambas credenciales viven en `~/.config/gcloud/` y guardan un *refresh token* que no vence solo: quien lea esos archivos
puede actuar como tú en GCP. Barreras en `.claude/settings.json`:
- `deny` de lectura sobre `~/.config/gcloud/**`: seguro para la herramienta Read; sobre Bash, `cat`/`head`/`sed`
  quedan bloqueados (probado), pero es una protección de mejor esfuerzo.
- `deny` de los comandos que imprimen tokens: `gcloud auth print-*`, `gcloud auth application-default print-*`,
  `gcloud config config-helper`.
- `ask` sobre `gcloud auth *`: el asistente no puede autenticar ni revocar sin permiso.

**Riesgo residual (aceptado mientras dure la prueba gratuita):** las reglas no frenan `grep -r` ni un subproceso
cualquiera que lea el archivo, ni variantes con opciones globales antes del subcomando (`gcloud --project X auth print-...`);
eso solo lo haría el sandbox de Claude Code, que se reevalúa **al pasar a cuenta pagada**. Desde el 2026-11-06 el proyecto
usa la prueba gratuita de GCP (`billingEnabled: true`): Google no cobra durante la prueba, así que una credencial filtrada
podría gastar crédito o crear recursos, pero no cobrar a la tarjeta; el presupuesto (CLP 10.000 mensual) avisa por correo.
Quien tenga la credencial actúa como tu usuario en todos los recursos de GCP de la cuenta.

Tampoco puedo tocar la facturación sin permiso: `ask` sobre `gcloud billing *`.

Revocar (si se sospecha una fuga, o al terminar):

```bash
gcloud auth application-default revoke
gcloud auth revoke
```

### Transformación (Dataform)

El proyecto Dataform (SQLX) vive en `transform/`. Su CLI es una herramienta de desarrollo y CI: en producción, Dataform
corre como servicio administrado de Google (ADR-0001), por eso Node no va en la imagen de ingesta.

Requisitos: credenciales de GCP (arriba) y Node.js con [nvm](https://github.com/nvm-sh/nvm) (versión en `.nvmrc`,
como `.python-version` para Python):

```bash
nvm install                # instala la versión de .nvmrc
make transform-setup       # instala la CLI de Dataform fijada en package-lock.json (en ./node_modules)
npx dataform init-creds transform   # una vez: elegir ADC; crea transform/.df-credentials.json (sin secretos, ignorado por git)
make transform-compile     # compila el SQLX sin tocar BigQuery
make transform             # ejecuta contra BigQuery (datasets en us-central1)
```

El proyecto GCP y la región están en `transform/workflow_settings.yaml`, el archivo de configuración propio de Dataform
(excepción a la regla de configurar por variables de entorno; ver ADR-0001).

Por defecto solo se usan `table` y `view`; `incremental` requiere un ADR. En el sandbox (sin facturación, hasta el
2026-11-06) una tabla `incremental` funcionaba la primera vez y fallaba desde la segunda, porque usa DML.
