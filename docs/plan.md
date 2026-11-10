# Síntesis Económica V2 — Plan de proyecto de Data Engineering en GCP

> Documento de planificación. V1 (`/V1`) es referencia funcional; V2 se construye en una carpeta/repositorio nuevo
> y no reutiliza su estructura, solo su conocimiento de las fuentes (cómo se scrapea cada una, qué series se usan,
> qué validaciones importan).

---

## 1. Diagnóstico de V1: qué lo hace dependiente de ti

V1 funciona, pero solo en tu PC y con tu intervención. Las dependencias concretas:

| Dependencia | Dónde está | Por qué impide correrlo en otro entorno |
|---|---|---|
| Rutas Windows a Google Drive (`I:\Mi unidad\...`) | `scripts/core/registro.py`, `sintesis/config.yaml` | Ningún servidor tiene esa unidad |
| **Power Query en Excel** como capa de transformación | `Tabulado_INE_Regional.xlsx` + `sintesis/lectores/base.py` | Requiere Excel de escritorio y refresco manual. Es el eslabón que más amarra el proceso a una persona |
| Estado en archivo JSON junto al código | `core/estado_descargas.json`, `fuentes_urls.json` | No es concurrente, se pierde con el contenedor, no es auditable |
| Credenciales en `.env.local` plano | `core/config_local.py` | Correcto para local, inadecuado para nube (y la API BDE pasa usuario/clave en la URL: cuidado con logs) |
| Pasos manuales | nota IMACEC (PDF tras WAF), cifras de PDF vía GPT, textos GPT, venta de energía (datos de empresas), calendario Excel | No automatizables o no públicos |
| Sin control de versiones en V1, archivos `.bak`, `~$` | varios | Señal negativa en un repo público |
| Reintentos por bloqueo de Drive, copia plana desactivada, `va_a_central` | `almacenamiento.py` | Complejidad que existe solo por el sistema de archivos de Drive |
| User-Agent que simula Chrome | `core/http.py` | En un proyecto profesional se usa un UA honesto con contacto y límites de frecuencia |

**Lo valioso que sí se rescata:** el conocimiento de cada fuente (endpoints del INE regional, POST `hijosCarpeta`/`getArchivos`
de los cuadros del INE, reparación de xlsx rotos, consulta avanzada del Senado), el mapeo tabla → series de `config.yaml`,
la lógica de desfase esperado por indicador (`verificar.py`) y las definiciones de KPI (`cifras.py`).

---

## 2. Objetivo de V2

Un pipeline ELT que **cualquier persona con un proyecto GCP pueda desplegar con `terraform apply` y correr sin ti**,
y que demuestre las competencias que piden roles de data engineer junior / desarrollador externo en entornos GCP:

- Ingesta containerizada (Docker) corriendo en **Cloud Run Jobs**, programada con **Cloud Scheduler**.
- Data lake en **Cloud Storage** (capa raw inmutable) y warehouse en **BigQuery**.
- Transformación y calidad de datos con **Dataform** (assertions, linaje, documentación; ADR-0001, que reemplazó a dbt).
- Infraestructura como código con **Terraform**, incluido IAM con mínimo privilegio y **Secret Manager**.
- CI/CD con **GitHub Actions** autenticado vía **Workload Identity Federation** (sin llaves JSON).
- Observabilidad: logs estructurados, tabla de auditoría de ejecuciones, alertas.
- (Opcional, al final) el mismo contenedor como **CronJob de Kubernetes** (kind local → GKE Autopilot).

### Qué queda fuera de V2 (reducción deliberada)

| Función de V1 | Decisión en V2 | Motivo |
|---|---|---|
| Power Query | **Se reemplaza** por parsers Python + Dataform | Es el núcleo del ejercicio |
| Boletín PDF, correo Mailchimp, carrusel | Fuera del núcleo. Fase 7 opcional: un job que lee los marts y genera gráficos | La "última milla" editorial no es data engineering; V1 puede seguir usándose para publicar |
| Textos GPT, cifras desde PDF | Fuera | Proceso manual/semimanual, no reproducible |
| Venta de energía (Chilquinta/CGE) | Fuera (o datos sintéticos claramente rotulados) | Datos no públicos: no pueden ir en un repo público |
| Nota de prensa IMACEC (PDF tras WAF) | Fuera. **IMACEC se obtiene de la API BDE** del Banco Central | No se evade un WAF; la API es la vía oficial |
| Calendario de publicaciones en Excel | CSV versionado cargado a BigQuery (equivalente a un *seed*; se define en la fase 2) | Versionable y testeable |
| `estado_descargas.json`, `_Histórico/`, `reporte.py` | Tabla de auditoría en BigQuery + versionado/ciclo de vida de GCS | Idempotencia por hash, no por nombre de archivo |
| Aduana | Opcional (fase tardía) | Suma volumen, no competencias nuevas |

### Alcance mínimo viable (MVP)

Tres fuentes que cubren tres patrones de extracción distintos:

1. **Banco Central API BDE** — UF + IMACEC (API autenticada, JSON, secreto en Secret Manager). Verificar códigos de serie con `SearchSeries` antes de usarlos.
2. **INE Regional** (empleo, ISUP, IPMAN, energía, exportaciones) — API de noticias + scraping HTML + parseo de xlsx desordenados.
3. **Senado** — consulta GET + tabla HTML (dato no numérico: muestra modelado de otro tipo de entidad).

INE nacional / cuadros estadísticos (POST + reparación de xlsx) se agregan en una segunda iteración una vez estable el patrón.

---

## 3. Arquitectura objetivo

```
Cloud Scheduler (cron mensual/diario)
        │  (SA: sa-scheduler → roles/workflows.invoker)
        ▼
Cloud Workflows: pipeline_sintesis
        ├─▶ Cloud Run Job  "ingest"   (SA: sa-ingest)
        │       fuente → GCS raw (archivo original, inmutable)
        │       parser → BigQuery raw.observations (formato largo)
        │       registro → BigQuery ops.runs (auditoría)
        ├─▶ Dataform (invocado por Workflows; SA: sa-dataform)
        │       tablas stg/marts + assertions (ADR-0001)
        └─▶ en error: log estructurado → alerta (Cloud Monitoring → email)

Consumo: Looker Studio sobre marts  |  (opcional) job "reportes" que genera gráficos desde marts
```

**Por qué Cloud Workflows y no Composer/Dagster (decidido, ver ADR-0002):** Composer (Airflow gestionado) tiene costo
fijo alto. Dagster habría que alojarlo (Dagster+ es pago; autoalojado requiere un servicio siempre encendido y una base
de datos), y a esta escala (≈ 10 fuentes, corrida diaria o mensual, una dependencia lineal ingest → Dataform) no aporta
nada que Workflows no haga. Workflows es nativo, cae en el nivel gratuito y obliga a entender IAM entre servicios.
Dataform ya entrega el grafo de dependencias y el linaje de la parte de transformación.

### Capas de datos

| Capa | Dónde | Contenido | Regla |
|---|---|---|---|
| Landing / raw files | `gs://<proyecto>-raw/source=<fuente>/dataset=<x>/ingest_date=AAAA-MM-DD/<sha256>_<nombre>` | Archivo tal como lo entrega la fuente | Inmutable. Mismo hash = no se vuelve a subir |
| Raw tables | BigQuery `raw` | `observations`: `source_id, series_id, period (DATE), value (BIGNUMERIC), file_sha256, raw_path, ingest_date (DATE)` | Todas las ediciones; se recarga completa (`WRITE_TRUNCATE`). Partición mensual por `ingest_date`, cluster por `(source_id, series_id)` (2.2) |
| Staging | `stg` (Dataform) | Tipos, nombres, deduplicación, **última vintage por (serie, periodo)** | Una vista por fuente |
| Marts | `marts` (Dataform) | `dim_series`, `fct_observations_monthly`, `mart_kpi_edition`, `mart_indicator_comparison`, `mart_published_laws` (nombres en inglés propuestos en la 2.2; se confirman en 2.3/2.5 y fase 6) | Lo que consume el reporte/dashboard |
| Ops | `ops` | `runs` (`run_id, source_id, started_at, status, new_files, existing_files, rows_written, duration_s, error`) | Reemplaza `reporte.py` y el JSON de estado |

**Concepto clave a demostrar: vintages.** El INE y el Banco Central revisan cifras. Guardar cada carga con su
`ingest_date` (fecha del primer guardado del raw) permite reconstruir "qué cifra se publicó en la edición de septiembre" versus "cuál es la cifra vigente hoy".
Es un tema que aparece en entrevistas y V1 no lo resuelve.

### Identidades y accesos (diseño IAM)

| Service account | Permisos (a nivel de recurso, no de proyecto cuando sea posible) |
|---|---|
| `sa-ingest` | `storage.objectCreator` en bucket raw · `bigquery.dataEditor` en dataset `raw` y `ops` · `bigquery.jobUser` en proyecto · `secretmanager.secretAccessor` **solo** en el secreto de la API BDE |
| `sa-dataform` (a confirmar en la fase 3) | `bigquery.dataViewer` en `raw` · `bigquery.dataEditor` en `stg`, `marts` · `bigquery.jobUser` |
| `sa-workflows` | `run.invoker` (o `run.developer` para ejecutar jobs) sobre los dos jobs · `logging.logWriter` |
| `sa-scheduler` | `workflows.invoker` sobre el workflow |
| `sa-ci` (GitHub Actions vía WIF) | `artifactregistry.writer` en el repo de imágenes · permisos de deploy acotados · lectura del bucket de estado de Terraform |
| Tu usuario | Owner solo en el proyecto dev; en prod, viewer + capacidad de impersonar `sa-ci` para emergencias |

Reglas: ninguna llave JSON descargada; ningún rol `editor`/`owner` a service accounts; cada permiso justificado en un ADR.

---

## 4. Estructura del repositorio V2

```
sintesis-economica-v2/
├── README.md                 # qué es, diagrama, cómo desplegar desde cero
├── CLAUDE.md                 # convenciones para Claude Code (ver sección 7)
├── docs/
│   ├── adr/                  # 0001-elt-con-bigquery.md, 0002-workflows-vs-composer.md, ...
│   └── fuentes.md            # ficha por fuente (heredada del conocimiento de V1)
├── ingest/                   # paquete Python (uv + pyproject.toml)
│   ├── src/sintesis_ingest/
│   │   ├── config.py         # pydantic-settings: todo por variables de entorno
│   │   ├── sources.yaml      # reemplaza BOLETINES de registro.py
│   │   ├── http.py           # cliente con reintentos, backoff, UA honesto, rate limit
│   │   ├── storage.py        # interfaz: LocalStorage | GCSStorage
│   │   ├── warehouse.py      # carga a BigQuery (load jobs, no streaming)
│   │   ├── audit.py          # registro de ejecuciones
│   │   ├── connectors/       # bcentral_api.py, ine_regional.py, senado.py, ...
│   │   ├── parsers/          # xlsx/html → filas (serie, periodo, valor); reparar_xlsx.py
│   │   └── cli.py            # `sintesis-ingest run --source ine_regional --env dev`
│   ├── tests/
│   │   ├── fixtures/         # HTML/JSON/xlsx reales guardados (de /V1/input)
│   │   └── test_*.py
│   └── Dockerfile
├── transform/                # repositorio Dataform (ADR-0001)
│   ├── models/{staging,marts}/
│   ├── seeds/                # (histórico, plan dbt) dim_series: desfase esperado, unidad, fuente; calendario
│   ├── tests/                # tests genéricos propios (p. ej. dato_al_dia)
│   ├── profiles.yml          # usa env_var(); method: oauth (ADC)
│   └── Dockerfile
├── infra/                    # Terraform
│   ├── bootstrap/            # bucket de estado, APIs, WIF (se aplica una vez, a mano)
│   ├── modules/{ingest_job,dataform,pipeline}/
│   └── envs/{dev,prod}/      # main.tf + terraform.tfvars
├── orchestration/workflow.yaml
├── k8s/                      # fase 8 opcional: cronjob.yaml
├── .github/workflows/        # ci.yml (PR), deploy.yml (main)
├── docker-compose.yml        # correr ingest localmente con almacenamiento local
├── Makefile                  # make test | make run-local | make transform | make plan
└── .pre-commit-config.yaml   # ruff, ruff-format, sqlfluff, terraform fmt, detect-secrets
```

---

## 5. Fases

Cada fase termina en algo que funciona y se puede mostrar. No pasar a la siguiente sin cumplir el "listo cuando".

**Estrategia: rebanada vertical (*walking skeleton*), decidida el 2026-11-02.** Primero una sola fuente, el Banco
Central (UF/IMACEC), recorre todo el pipeline: ingesta → BigQuery → Dataform → Terraform → orquestación → CI/CD.
Después se ensancha con las demás fuentes (fase 6). Motivos: los riesgos (Dataform con el sandbox) y las competencias
menos conocidas están en las fases de nube; un pipeline completo con una fuente vale más que uno a medias con tres; y el
contrato de conectores (ADR-0003) se valida con una fuente real antes de generalizarlo.

**Orden = numeración (por el costo, sección 6):** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. La prueba gratuita se activó
**durante la fase 2** (2026-11-06, tarea 2.2a; vence ~2027-02-04), no al inicio de la 3 como se había planeado: ver §6. La fase 2 usa autenticación con tu usuario (`gcloud auth application-default login`); en la fase 4 pasa
a la service account `sa-dataform`.

> **Renumeración (2026-11-02).** Antes → ahora: 1 → 1 (solo Banco Central) · 3 → 2 · 2 → 3 · 4 → 4 · 5 → 5 · (nueva) → 6
> ensanche · 6 → 7 · 7 → 8. Los planes de tareas cerradas antes de esa fecha usan la numeración anterior.

### Fase 0 — Fundaciones (local, sin GCP) · ~1 semana
**Aprendes:** estructura de proyecto Python profesional, git, tooling.
- Repo git nuevo (público desde el inicio o cuando esté limpio, ver D1). `.gitignore` estricto; `detect-secrets` en pre-commit.
- `uv` + `pyproject.toml`, `ruff`, `pytest`, `pre-commit`.
- `config.py` con `pydantic-settings`: cero rutas escritas en el código.
- `sources.yaml` + modelo pydantic que lo valida (reemplaza el dict `BOLETINES`).
- Logging estructurado JSON (`logging` + formatter; campos `run_id`, `source_id`, `severity`) — Cloud Logging lo interpreta solo.
- Copiar a `tests/fixtures/` una muestra de los xlsx/PDF de `/V1/input` y HTML guardados de cada fuente.
- **Listo cuando:** `make test` pasa en una máquina limpia y `pre-commit run --all-files` no reclama.

### Fase 1 — Ingesta del Banco Central + Docker · ~1–2 semanas
**Aprendes:** diseño de conectores, idempotencia, contenedores, manejo de secretos en local.
- Ficha de la fuente (`v1-analista`) y códigos de serie de UF e IMACEC verificados con `SearchSeries`.
- Contrato común (ADR-0003): el conector solo descarga; `Storage` local idempotente por `sha256` (si el objeto existe, no se sube ni se recarga); cliente HTTP común (User-Agent honesto, pausa, reintentos, redacción de credenciales).
- Parser del JSON → formato largo `(series_id, period, value)`. Solo limpieza estructural; **los cálculos (var. 12 meses, KPI) van a Dataform**.
- Tests contra un fixture JSON real, sin credenciales.
- CLI `sintesis-ingest run --source <id>`, registro de ejecuciones y `make run-local`.
- `Dockerfile` multi-stage, imagen slim, usuario no root; `docker compose run ingest`.
- (Opcional) experimento `experiment/dlt-bde` (ADR-0003).
- **Listo cuando:** con Docker, una corrida baja UF e IMACEC, deja el JSON en `./data/raw` y las observaciones en parquet/CSV, y una segunda corrida no duplica nada.

### Fase 2 — BigQuery + Dataform (empezó en el sandbox; prueba gratuita desde la 2.2a) · ~2 semanas
> **Nota (2026-11-04, tarea 2.1):** go/no-go de Dataform con el sandbox = **GO** (ADR-0001, Consecuencias). Los puntos
> de esta fase y de la 5 se reescribieron con sus equivalentes en Dataform. Restricciones verificadas del sandbox:
> sin DML (las tablas `incremental` funcionan la 1.ª vez y fallan desde la 2.ª) y sin Cloud Storage (exige facturación).
> Desde la 2.2a (2026-11-06) hay facturación (prueba gratuita): ambas restricciones ya no aplican.

**Aprendes:** modelado analítico, Dataform, calidad de datos, costos de BigQuery.
- ~~Go/no-go de Dataform con el sandbox~~ → **GO** (2.1). Región `us-central1` (decisión de Rafael). Desarrollo con la
  CLI local (`make transform-compile` / `make transform`), sin repositorio de Dataform en GCP hasta la fase 3/4.
- Alcance de la rebanada: solo las series del Banco Central (UF, IMACEC). Las demás fuentes se modelan en la fase 6.
- `warehouse.py`: carga con *load jobs* **desde archivos locales** (decisión de alcance: el bucket raw se crea con Terraform en la fase 3), esquema
  explícito, tabla particionada y clusterizada. `value` no cabe en `NUMERIC` (el Banco Central entrega 11 decimales):
  decidir entre `BIGNUMERIC`, `FLOAT64` o texto en raw.
- Dataform: tablas raw como `declaration`; **frescura** como assertion propia (según la documentación, Dataform no trae `freshness`; reemplaza
  parte de `verificar.py`); staging por fuente; dedupe de vintages; marts.
- Tablas de referencia (Dataform no tiene *seeds*; candidatos para la 2.3: CSV versionado cargado con `bq load` y
  declarado, o SQLX con `VALUES`): `dim_series` (id, nombre, unidad, fuente, frecuencia, `desfase_meses` heredado de `config.yaml` de V1), calendario.
- Assertions: `uniqueKey`/`nonNull`/`rowConditions` (integradas) y propias para relaciones y valores aceptados, y uno propio `dato_al_dia(desfase_meses)` que reproduce la lógica "dato esperado vs último dato" de V1. Atípicos (variación fuera de N desviaciones) como aviso: en Dataform una assertion falla o no falla, así que el aviso
  se resuelve aparte (p. ej. una tag que no corta la corrida).
- Lógica de `cifras.py` (KPI y comparaciones) traducida a SQL en marts.
- Documentación: Dataform no genera un sitio como `dbt docs`. Candidatos para la 2.6: descripciones en SQLX (a verificar
  que lleguen a BigQuery como descripciones de tablas y columnas) y el grafo de `dataform compile --json` publicado en CI o Pages.
- **Validación cruzada:** las cifras de `mart_kpi_edition` para una edición pasada deben coincidir con las publicadas por V1. Es la prueba de que la migración es correcta.
- **Listo cuando:** la transformación corre en dev sin errores y los KPI de UF/IMACEC de 2026-09 coinciden con el `contenido_2026-09.yaml` de V1 (el resto de los KPI, en la fase 6).
- **Pendiente (30-10-2026):** `contenido_2026-09.yaml` no está en la carpeta `/V1`; probablemente vive en Drive (`I:\Mi unidad\...`). Ubicarlo y copiarlo como fixture de referencia antes de la validación cruzada.

### Fase 3 — Fundación GCP con Terraform · ~1–2 semanas
> **La prueba gratuita ya está activa desde la fase 2** (2.2a, 2026-11-06; vence ~2027-02-04, sección 6): las fases 3, 4 y 5 deben caber en ese plazo.
**Aprendes:** Terraform, IAM, Secret Manager, gestión de costos.
- **Al pasar a cuenta pagada: reevaluar el sandbox de Claude Code** (postergado en la 1.1a, la 2.0 y la 2.2a. Al activar la prueba gratuita se reevaluó y se mantuvieron las reglas: durante la prueba Google no cobra, así que la credencial recién vale dinero real con la cuenta pagada). Alternativa a evaluar en la misma discusión: trabajar dentro de un *devcontainer* con impersonación de una service account (credenciales de vida corta), como hacen equipos con más infraestructura (idea de Rafael, 2.0).
  En la misma discusión, como concepto: un **hook de Claude Code** que revise la salida de cada comando y bloquee las
  credenciales reales antes de que lleguen a Claude (idea de Rafael, 1.2). Lo leería el script del hook, nunca Claude.
- `infra/bootstrap`: bucket de estado remoto (con versionado), habilitación de APIs, presupuesto con alertas (budget de billing).
- Recursos: buckets (raw con lifecycle hacia Nearline/Coldline), datasets BQ (`raw`, `stg`, `marts`, `ops`) con descripción y labels, Artifact Registry, Secret Manager (el **valor** del secreto se carga a mano con `gcloud`, nunca en Terraform/tfvars), service accounts y bindings de la tabla IAM.
- Separación dev/prod (ver D3).
- Escribir los bindings IAM a mano tú mismo, aunque Claude Code proponga el resto: es lo que se pregunta en entrevistas.
- **Listo cuando:** `terraform destroy && terraform apply` reconstruye todo desde cero sin pasos de consola, salvo cargar el secreto.

### Fase 4 — Despliegue y orquestación · ~1–2 semanas
**Aprendes:** Cloud Run Jobs, Scheduler, Workflows, observabilidad.
- Módulos Terraform `ingest_job` (Cloud Run Job, cada uno con su SA, timeout, reintentos, límites de CPU/memoria).
- `workflow.yaml`: ingest → invocación de Dataform; manejo de error con log `severity=ERROR`.
- Cloud Scheduler con zona horaria `America/Santiago`.
- Alerta en Cloud Monitoring: política basada en logs de error del workflow/jobs → email.
- Riesgo a vigilar: algunos sitios del Estado bloquean IPs de nubes públicas. Si el INE bloquea Cloud Run, documentarlo en un ADR y evaluar alternativas legítimas (contactar a la fuente, frecuencia menor) antes que evasión.
- **Listo cuando:** el pipeline corre solo una vez programado, y un fallo provocado a propósito genera un correo.

### Fase 5 — CI/CD · ~1 semana
**Aprendes:** GitHub Actions, Workload Identity Federation, flujo de PR.
- `ci.yml` (en cada PR): ruff, pytest, `sqlfluff lint`, `dataform compile` + `dataform run --dry-run` (y luego `run`) con sufijo de dataset por PR (el `dry-run` valida
  contra tablas que ya existen: necesita un entorno con las tablas creadas), `terraform fmt -check` + `validate` + `plan` comentado en el PR.
- `deploy.yml` (merge a `main`): build y push de imágenes con tag del commit SHA, `terraform apply` en dev; prod con aprobación manual (GitHub Environments).
- Autenticación a GCP solo por WIF, restringida al repositorio y rama.
- Trabajar con ramas y PR aunque estés solo: el historial de PRs es parte del portafolio.
- **Listo cuando:** un cambio de una línea en un SQLX de Dataform llega a prod solo vía PR + aprobación.

### Fase 6 — Ensanche: Senado e INE · ~2–3 semanas
**Aprendes:** generalizar un contrato, scraping responsable, reemplazar una transformación manual (Power Query) con tests.
- Senado (ficha lista en `docs/fuentes.md`): conector, fixture HTML real, parser.
- INE regional: ficha, conector (API de noticias) y **un parser por archivo** (energía, exportaciones, IPMAN, ISUP), cada uno supervisado por Rafael (hojas, columnas, fechas, filas descartadas). Decidir cómo se obtiene empleo.
- `Storage` en GCS ya existe (fase 3): las fuentes nuevas solo se agregan a `sources.yaml` y se despliegan.
- Modelos de Dataform y KPI del resto de las fuentes; validación cruzada completa contra V1.
- 2.ª iteración: INE nacional / cuadros estadísticos (POST + reparación de xlsx).
- Puede ocurrir después de terminada la prueba gratuita: se desarrolla en local y sandbox.
- **Listo cuando:** las 3 fuentes del MVP corren en el pipeline y los KPI de 2026-09 coinciden con V1.

### Fase 7 — Consumo (opcional pero recomendable) · ~1 semana
- Dashboard en Looker Studio sobre `marts` (enlace en el README). Gratis y funciona también contra el sandbox.
- Boletín, correo y gráficos quedan fuera de V2 (decidido).

### Fase 8 — Kubernetes (opcional, aprendizaje) · ~1 semana
- Primero en local con `kind`: el mismo contenedor de ingest como `CronJob`, `Secret`, `ConfigMap`, `ServiceAccount`.
- Después GKE Autopilot con Workload Identity (la SA de Kubernetes impersona `sa-ingest`), corrida de prueba y **destruir el clúster**. Revisar precios vigentes antes: un clúster tiene costo mientras exista.
- ADR explicando por qué en producción se queda en Cloud Run (es la decisión correcta a esta escala; saber justificarlo vale más que tener el clúster encendido).

---

## 6. Costos y cuidado de la cuenta

### Restricción: sandbox y prueba gratuita

- **BigQuery sandbox** (sin tarjeta): 10 GiB de almacenamiento (tope de por vida), 1 TiB de consulta al mes,
  tablas y particiones que se borran a los 60 días, **sin DML** (`INSERT/UPDATE/MERGE`) y sin streaming.
  No da acceso a Cloud Run, Scheduler, Workflows, Secret Manager ni Artifact Registry: todos exigen cuenta de facturación.
- **Prueba gratuita:** USD 300 por 90 días. Pide tarjeta, pero no cobra: si no se actualiza manualmente a cuenta
  pagada, al terminar se cierra y los recursos se detienen (30 días de gracia). El reloj de 90 días corre desde la activación.
- Consecuencia en el diseño:
  1. Fases 0 y 1 sin tarjeta; la fase 2 empezó en el sandbox (2.0–2.1: go/no-go de Dataform).
  2. **Cambio (2026-11-06, 2.2a):** la prueba gratuita se activó durante la fase 2, no al inicio de la 3. Motivo
     (Rafael): demostrar GCP como lo opera una empresa; los límites del sandbox (sin DML, sin Cloud Storage, expiración
     de 60 días) agregaban ruido. Su límite personal es febrero de 2027, así que el reloj sirve. Vence ~**2027-02-04**:
     las fases 2–5 deben caber; el ensanche (fase 6) se recorta si no alcanza.
     Presupuesto adelantado desde la fase 3: **CLP 10.000 mensual**, alertas 50/90/100 % (se reproduce en Terraform).
  3. Tablas de Dataform como `table`/`view` por defecto; `incremental` (con `merge`) solo como mejora documentada en un
     ADR. La capa raw se recarga completa desde los archivos con *load jobs* (`WRITE_TRUNCATE`): los archivos raw son la
     fuente de verdad y BigQuery se puede reconstruir en cualquier momento. Nació como restricción del sandbox; se
     mantiene por buena práctica.
  4. (Sandbox, histórico) La expiración de 60 días ya no aplica a los datasets creados desde el 2026-11-06.
- **Pendiente (enero de 2027):** decidir entre pasar a cuenta pagada (los recursos siguen; cobra lo que exceda el
  nivel gratuito) o cerrar. Si la cuenta de prueba se cierra: recursos detenidos, 30 días de gracia y luego borrado.
- Al cerrar la prueba: `terraform destroy` y el repo queda como evidencia (README, capturas, linaje de Dataform, historial de CI).

### Uso del crédito

- Todo el núcleo (Cloud Run Jobs ocasionales, Scheduler con pocos jobs, Workflows con pocos pasos, BigQuery con MB de datos, GCS con cientos de MB) debería caer en o cerca del nivel gratuito. Verificar en las páginas de precios vigentes antes de la fase 3.
- Presupuesto con alertas al 50/90/100 % desde el primer `apply`.
- Evitar: Composer, clústeres GKE encendidos, `SELECT *` sin filtro de partición, conectores de Looker Studio que consulten tablas sin particionar en cada carga.
- Labels (`proyecto`, `entorno`, `componente`) en todos los recursos para ver el costo por componente.

---

## 7. Forma de trabajo con Claude Code

Incorpora `claude/traspaso-flujo-trabajo-claude-code.md` (Project), con ajustes. Regla base del traspaso, que se adopta
sin cambios: **Claude construye, verifica y gestiona contexto; Rafael decide, valida y aprueba.** Toda tarea termina
en un punto de validación explícito.

### 7.1 Principios adoptados

1. **El contexto vive en el repo, no en los chats.** `CLAUDE.md`, `docs/plan.md` (este archivo, movido al repo), `docs/adr/`, `docs/fuentes.md`.
2. **Una sesión por tarea, corta.** Sesión nueva cuando cambia la tarea o el contexto se llenó.
3. **Plan primero.** Plan mode en toda tarea no trivial; obligatorio en Terraform, IAM y tablas nuevas de Dataform.
4. **Delegación por riesgo:** lectura → verificación → construcción. Sin modo auto ni bypass de permisos durante el proyecto.
5. **Lo que se pregunta en entrevistas lo hace Rafael:** bindings IAM, decisión de cada ADR, valores de referencia de los tests, validación cruzada con V1, merge a `main`.
6. **Configurar por necesidad.** Skills, hooks y subagentes nuevos se crean tras repetir algo 2–3 veces.
7. **La máquina revisa formato; Rafael revisa diseño, lógica y cifras.**

### 7.2 Ajustes al traspaso (contraste con el objetivo del proyecto)

El objetivo es un pipeline que corra sin ti **y** que tú puedas defender. El traspaso empuja bien lo segundo, pero
propone más herramientas de flujo de las que conviene sumar al mismo tiempo que aprendes git, Docker, dbt y GCP.
El riesgo concreto es que la fase 0 se vuelva meta-trabajo y la ingesta no parta. Ajustes:

| Propuesta del traspaso | Ajuste | Motivo |
|---|---|---|
| `CLAUDE.md` raíz + anidados desde fase 0 | Solo raíz en fase 0. Anidados (`ingest/`, `transform/`, `infra/`) cuando cada carpeta tenga código | Un `CLAUDE.md` sobre carpetas vacías es especulación |
| 3 subagentes de etapa A en fase 0 | Solo `v1-analista`. `Explore` ya viene incluido. `revisor-convenciones` cuando existan convenciones que revisar (fin de fase 1) | Menos piezas que entender a la vez |
| Hook de lint en fase 0 | Pre-commit es la única fuente de verdad del lint (es lo que también corre en CI). Hook opcional que solo llama a `ruff` sobre el archivo editado | Evita dos configuraciones de lint que divergen |
| Worktrees desde fase 1 | **Al final de fase 1**, después de haber hecho al menos 3 PR normales con ramas | Worktrees sobre un git que aún no dominas multiplican los errores de estado. Primero ramas y PR; después paralelismo |
| Etapa C tras 2 parsers revisados | Se mantiene, con un criterio extra: poder explicar sin ayuda qué prueba cada test de esos dos parsers | El criterio es comprensión, no cantidad |
| MCP para BigQuery en fase 2 | No. Claude usa `bq` CLI con tu usuario y tú ves los comandos | Un comando visible es más auditable y enseña la CLI que se usa en el trabajo |
| `test-runner` como subagente | Sí, desde fase 1 | Es el que más protege el contexto de la sesión principal (logs largos) |
| `docs/plans/` | Sí, versionado en el repo público, máximo una página por plan | Muestra proceso; el tope evita ruido |
| Cowork como espacio de planificación | Sí. Su resultado siempre termina como archivo en el repo (`docs/plan.md`, ADR) | Principio 1 |
| Más de 2 sesiones en paralelo | No durante este proyecto | Con 2 ya validas todo lo que produce; más rompe el principio 5 |

### 7.3 Ciclo estándar por tarea

1. Sesión nueva en VS Code (ventana WSL) → plan mode → Claude lee `CLAUDE.md`, `docs/plan.md` y ADR relevantes.
2. Plan iterado contigo → guardado en `docs/plans/AAAA-MM-DD-<tarea>.md`.
3. Rama nueva → ejecución con aprobación de ediciones.
4. `make test` (o `test-runner`) hasta pasar.
5. **Tu validación:** diff, resultados, cifras de referencia.
6. Cierre: docs actualizadas; ADR si hubo decisión (decisión escrita por ti); regla nueva en `CLAUDE.md` si hubo un error repetido.
7. Commit pequeño → PR → merge tuyo.

### 7.4 Subagentes y skills por fase

| Fase | Se agrega |
|---|---|
| 0 | `CLAUDE.md` raíz, `docs/{plans,adr}/`, `.claude/agents/v1-analista.md` (solo lectura sobre V1). Probar plan mode en una tarea chica |
| 1 | `test-runner`; ficha de `v1-analista` del Banco Central; `revisor-convenciones` y worktrees al cierre de la fase |
| 2 | `validador-cifras` (marts vs `contenido_AAAA-MM.yaml` de V1); skill `agregar-serie` |
| 3 | `revisor-iam` (solo lectura). Terraform siempre en plan mode; tú escribes IAM y corres `apply` |
| 4–5 | Revisor de PR antes de cada merge (`cerrar-tarea` ya existe desde la fase 0) |
| 6 | Fichas de `v1-analista` de Senado e INE; skill `agregar-fuente` después del 2.º conector nuevo |
| Cierre | Retrospectiva en `docs/retrospectiva.md`: qué se delegó, qué no, qué reglas nacieron de errores. Material de entrevista |

Las funciones de Claude Code cambian seguido: verificar cada una en https://code.claude.com/docs al configurarla.

### 7.5 Fase 0 desglosada (primer bloque de trabajo en VS Code)

Tope: **2 días para el flujo de trabajo**, el resto de la fase es código.

| # | Tarea | Quién | Listo cuando |
|---|---|---|---|
| 0.1 | Verificar entorno WSL: `docker run hello-world`, `uv`, `git`, `gcloud`, `terraform` | Tú, Claude guía | Todos responden |
| 0.2 | `git init` en `~/projects/sintesis-economica-v2`, `.gitignore`, `.gitattributes`, repo en GitHub (privado hasta limpiarlo) | Tú | Primer commit pusheado |
| 0.3 | Mover este plan a `docs/plan.md`; crear `CLAUDE.md` raíz (borrador en anexo A) | Claude propone, tú apruebas | Commit |
| 0.4 | `.claude/agents/v1-analista.md` | Claude propone, tú lees la definición | Primera ficha de prueba (Senado) en `docs/fuentes.md` |
| 0.5 | `pyproject.toml` con uv, ruff, pytest, pre-commit (+ detect-secrets) | Claude, en plan mode | `pre-commit run --all-files` limpio |
| 0.6 | `config.py` (pydantic-settings) y `sources.yaml` + validación | Claude | Test que falla con un YAML inválido |
| 0.7 | Logging JSON | Claude | Test que verifica el formato |
| 0.8 | Copiar fixtures desde V1 (`/V1/input`, HTML guardados) | Claude | Fixtures en `ingest/tests/fixtures/`, sin datos privados |
| 0.9 | ADR-0001 (ELT con GCS + BigQuery + dbt) y ADR-0002 (Workflows, sin Dagster) | Claude borrador de contexto/opciones; **tú la decisión** | Dos ADR en `docs/adr/` |

**Migración desde V1:** no se copia código de V1 al repo. Por cada fuente: ficha de `v1-analista` → la validas → plan →
implementación nueva con tests. Las credenciales de `.env.local` de V1 no se copian: en local van como variable de
entorno en WSL (fuera del repo) y en la nube a Secret Manager.

### Anexo A — Borrador de `CLAUDE.md` raíz

```markdown
# Síntesis Económica V2

Pipeline ELT de indicadores económicos de la Región de Valparaíso y Chile: descarga → GCS (raw) → BigQuery → dbt.
Proyecto de portafolio: debe correr sin intervención de su autor y cada decisión debe poder defenderse.
Plan completo: docs/plan.md. Decisiones: docs/adr/. Fuentes: docs/fuentes.md.

## Forma de trabajo
- Toda tarea no trivial empieza en plan mode. El plan aprobado se guarda en docs/plans/AAAA-MM-DD-<tarea>.md.
- Rafael valida y aprueba; no hacer merge, no correr `terraform apply`, no cambiar IAM sin que él lo pida.
- Bindings IAM y la sección "Decisión" de los ADR los escribe Rafael. Claude puede revisarlos y explicarlos.
- Al cerrar una tarea, listar explícitamente qué debe validar Rafael (diff, cifras, resultados).
- Explicar el porqué de cada decisión no obvia; Rafael está aprendiendo y debe poder defenderla.

## Reglas
- V1 (/mnt/c/Users/rafae/Workspace Rafael/02_Trabajo/Codes/Sintesis Economica/V1) es solo lectura. No copiar su código: portar con tests.
- Sin rutas absolutas en el código. Toda configuración por variables de entorno (pydantic-settings) o sources.yaml.
- Nunca credenciales en código, tfvars, fixtures ni logs. La API BDE pasa usuario/clave en la URL: no loguear URLs completas.
- Raw es inmutable e idempotente por sha256. Los cálculos (variaciones, KPI) van en dbt, no en Python.
- BigQuery sandbox hasta la fase 2: sin DML; modelos dbt como table/view; raw se recarga con load jobs WRITE_TRUNCATE.
- User-Agent honesto con contacto y pausa entre solicitudes. No evadir bloqueos (WAF) de las fuentes.

## Comandos
- make test · make lint · make run-local SOURCE=<id> · make dbt-build   (se completan a medida que existan)

## Convenciones
- Código e identificadores en inglés; documentación de dominio en español (D5).
- Commits pequeños, una rama y un PR por tarea.
```

---

## 8. Decisiones

Tomadas (30-10-2026):
- **Alcance:** solo descarga, transformación y almacenamiento. Fuera: venta de energía, boletín, correo, textos. Kubernetes queda opcional.
- **Cuenta:** GCP personal, sin gasto: sandbox primero, prueba gratuita después (sección 6).
- **Orquestación:** Cloud Scheduler + Workflows. Sin Dagster.
- **Forma de trabajo:** principios del traspaso de Claude Code adoptados con los ajustes de la sección 7.2.
- **Prioridad:** este proyecto va primero. Del ETL personal solo se reutiliza el entorno WSL2 + Docker + uv (sección 9).
- **Estrategia de fases (2026-11-02):** rebanada vertical con el Banco Central (UF/IMACEC) de punta a punta; ensanche con Senado e INE en la fase 6. Fases renumeradas para que el número coincida con el orden (sección 5).
- **D5 — Idioma del código:** código e identificadores en inglés; documentación de dominio (ADR, fichas de fuentes, plan) en español. Los ids de fuentes y series son datos del dominio y van en español (`snake_case`), igual que los verán GCS y BigQuery (ajuste del 30-10-2026, tarea 0.6).

Abiertas:
- **D1 — Repo público:** recomendado (es el portafolio). Implica sin datos de empresas, sin marca ASIVA, sin credenciales en el historial. Si alguna vez la clave de la API BDE estuvo en un repo, rotarla.
- **D3 — Entornos:** con la prueba gratuita, un solo proyecto GCP con datasets `dev_*`/`prod_*` y Terraform parametrizado por entorno (dos proyectos duplican recursos y consumen crédito sin enseñar mucho más). El README explica cómo sería con dos proyectos.
- **Policy tags (sugerencia de un experto, 2026-11-03):** marcar las columnas sensibles con *policy tags* de BigQuery
  (seguridad por columna: solo ciertos grupos las ven). Hoy las fuentes son estadísticas públicas sin datos personales,
  así que su valor sería demostrar la técnica. Evaluar en la fase 3: si requiere facturación y qué columna lo justificaría.

## 9. Entorno de desarrollo (heredado del ETL personal)

Del ETL personal solo existe el entorno: WSL2 + Docker + uv + `.gitignore`. Se reutiliza tal cual y se descarta el resto.

- **El repo V2 vive en el sistema de archivos de Linux** (`~/projects/sintesis-economica-v2`), no en `/mnt/c/...`:
  Docker, uv y git son mucho más lentos sobre el disco de Windows, y los permisos/fin de línea dan problemas.
- VS Code abierto con la extensión **WSL** ("Connect to WSL"), y Claude Code corriendo dentro de esa ventana, en esa carpeta.
- V1 se queda en Windows como referencia de solo lectura; se consulta desde WSL en
  `/mnt/c/Users/rafae/Workspace Rafael/02_Trabajo/Codes/Sintesis Economica/V1`. Los fixtures de prueba se **copian** al repo V2.
- `.gitattributes` con `* text=auto eol=lf` desde el primer commit.
- Docker Desktop con backend WSL2 (o Docker Engine nativo dentro de WSL). Las imágenes son Linux, igual que en Cloud Run.
- `gcloud` y `terraform` se instalan dentro de WSL, no en Windows, para no tener dos configuraciones de credenciales.
- Fase 0 incluye verificar el entorno: `docker run hello-world`, `uv --version`, `gcloud --version`, `terraform -version`, `git config user.email`.
