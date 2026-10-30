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
- Transformación y calidad de datos con **dbt** (tests, freshness, documentación).
- Infraestructura como código con **Terraform**, incluido IAM con mínimo privilegio y **Secret Manager**.
- CI/CD con **GitHub Actions** autenticado vía **Workload Identity Federation** (sin llaves JSON).
- Observabilidad: logs estructurados, tabla de auditoría de ejecuciones, alertas.
- (Opcional, al final) el mismo contenedor como **CronJob de Kubernetes** (kind local → GKE Autopilot).

### Qué queda fuera de V2 (reducción deliberada)

| Función de V1 | Decisión en V2 | Motivo |
|---|---|---|
| Power Query | **Se reemplaza** por parsers Python + dbt | Es el núcleo del ejercicio |
| Boletín PDF, correo Mailchimp, carrusel | Fuera del núcleo. Fase 6 opcional: un job que lee los marts y genera gráficos | La "última milla" editorial no es data engineering; V1 puede seguir usándose para publicar |
| Textos GPT, cifras desde PDF | Fuera | Proceso manual/semimanual, no reproducible |
| Venta de energía (Chilquinta/CGE) | Fuera (o datos sintéticos claramente rotulados) | Datos no públicos: no pueden ir en un repo público |
| Nota de prensa IMACEC (PDF tras WAF) | Fuera. **IMACEC se obtiene de la API BDE** del Banco Central | No se evade un WAF; la API es la vía oficial |
| Calendario de publicaciones en Excel | Seed CSV de dbt | Versionable y testeable |
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
        │       parser → BigQuery raw.observaciones (formato largo)
        │       registro → BigQuery ops.ejecuciones (auditoría)
        ├─▶ Cloud Run Job  "dbt"      (SA: sa-dbt)
        │       dbt source freshness → dbt build (modelos + tests)
        └─▶ en error: log estructurado → alerta (Cloud Monitoring → email)

Consumo: Looker Studio sobre marts  |  (opcional) job "reportes" que genera gráficos desde marts
```

**Por qué Cloud Workflows y no Composer/Dagster (decidido, ver ADR-0002):** Composer (Airflow gestionado) tiene costo
fijo alto. Dagster habría que alojarlo (Dagster+ es pago; autoalojado requiere un servicio siempre encendido y una base
de datos), y a esta escala (≈ 10 fuentes, corrida diaria o mensual, una dependencia lineal ingest → dbt) no aporta
nada que Workflows no haga. Workflows es nativo, cae en el nivel gratuito y obliga a entender IAM entre servicios.
dbt ya entrega el grafo de dependencias y el linaje de la parte de transformación.

### Capas de datos

| Capa | Dónde | Contenido | Regla |
|---|---|---|---|
| Landing / raw files | `gs://<proyecto>-raw/source=<fuente>/dataset=<x>/ingest_date=AAAA-MM-DD/<sha256>_<nombre>` | Archivo tal como lo entrega la fuente | Inmutable. Mismo hash = no se vuelve a subir |
| Raw tables | BigQuery `raw` | `observaciones`: `source_id, serie_id, periodo (DATE), valor (NUMERIC), unidad, archivo_uri, file_sha256, run_id, ingested_at` | Solo se agrega. Particionada por `ingested_at`, cluster por `serie_id` |
| Staging | `stg` (dbt) | Tipos, nombres, deduplicación, **última vintage por (serie, periodo)** | Una vista por fuente |
| Marts | `marts` (dbt) | `dim_serie`, `fct_observacion_mensual`, `mart_kpi_edicion`, `mart_comparacion_indicador`, `mart_proyectos_ley` | Lo que consume el reporte/dashboard |
| Ops | `ops` | `ejecuciones` (run_id, fuente, estado, archivos, filas, duración, error) | Reemplaza `reporte.py` y el JSON de estado |

**Concepto clave a demostrar: vintages.** El INE y el Banco Central revisan cifras. Guardar cada carga con su
`ingested_at` permite reconstruir "qué cifra se publicó en la edición de septiembre" versus "cuál es la cifra vigente hoy".
Es un tema que aparece en entrevistas y V1 no lo resuelve.

### Identidades y accesos (diseño IAM)

| Service account | Permisos (a nivel de recurso, no de proyecto cuando sea posible) |
|---|---|
| `sa-ingest` | `storage.objectCreator` en bucket raw · `bigquery.dataEditor` en dataset `raw` y `ops` · `bigquery.jobUser` en proyecto · `secretmanager.secretAccessor` **solo** en el secreto de la API BDE |
| `sa-dbt` | `bigquery.dataViewer` en `raw` · `bigquery.dataEditor` en `stg`, `marts` · `bigquery.jobUser` |
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
├── transform/                # proyecto dbt
│   ├── models/{staging,marts}/
│   ├── seeds/                # dim_serie.csv (desfase esperado, unidad, fuente), calendario.csv
│   ├── tests/                # tests genéricos propios (p. ej. dato_al_dia)
│   ├── profiles.yml          # usa env_var(); method: oauth (ADC)
│   └── Dockerfile
├── infra/                    # Terraform
│   ├── bootstrap/            # bucket de estado, APIs, WIF (se aplica una vez, a mano)
│   ├── modules/{ingest_job,dbt_job,pipeline}/
│   └── envs/{dev,prod}/      # main.tf + terraform.tfvars
├── orchestration/workflow.yaml
├── k8s/                      # fase 7 opcional: cronjob.yaml
├── .github/workflows/        # ci.yml (PR), deploy.yml (main)
├── docker-compose.yml        # correr ingest localmente con almacenamiento local
├── Makefile                  # make test | make run-local | make dbt-build | make plan
└── .pre-commit-config.yaml   # ruff, ruff-format, sqlfluff, terraform fmt, detect-secrets
```

---

## 5. Fases

Cada fase termina en algo que funciona y se puede mostrar. No pasar a la siguiente sin cumplir el "listo cuando".

**Orden de ejecución (por la restricción de costo, sección 6):** 0 → 1 → 3 (sobre BigQuery sandbox, en local) →
activar prueba gratuita → 2 → 4 → 5 → 6. La fase 3 sobre sandbox usa autenticación con tu usuario (`gcloud auth
application-default login`); en la fase 4 pasa a la service account `sa-dbt`.

### Fase 0 — Fundaciones (local, sin GCP) · ~1 semana
**Aprendes:** estructura de proyecto Python profesional, git, tooling.
- Repo git nuevo (público desde el inicio o cuando esté limpio, ver D1). `.gitignore` estricto; `detect-secrets` en pre-commit.
- `uv` + `pyproject.toml`, `ruff`, `pytest`, `pre-commit`.
- `config.py` con `pydantic-settings`: cero rutas escritas en el código.
- `sources.yaml` + modelo pydantic que lo valida (reemplaza el dict `BOLETINES`).
- Logging estructurado JSON (`logging` + formatter; campos `run_id`, `source_id`, `severity`) — Cloud Logging lo interpreta solo.
- Copiar a `tests/fixtures/` una muestra de los xlsx/PDF de `/V1/input` y HTML guardados de cada fuente.
- **Listo cuando:** `make test` pasa en una máquina limpia y `pre-commit run --all-files` no reclama.

### Fase 1 — Ingesta refactorizada + Docker · ~2 semanas
**Aprendes:** diseño de conectores, idempotencia, contenedores.
- Interfaz común: `Connector.discover() -> list[RemoteFile]`, `fetch()`, y un `Parser.parse(bytes) -> Iterable[Observation]`.
- Portar los 3 conectores del MVP desde V1 conservando la lógica de descubrimiento, sin la lógica de archivado en Drive.
- `Storage` con dos implementaciones (local y GCS). Idempotencia por `sha256`: si el objeto existe, no se sube ni se recarga.
- Parsers que reemplazan Power Query: cada xlsx → formato largo `(serie_id, periodo, valor)`. Solo limpieza estructural; **los cálculos (var. 12 meses, KPI) van a dbt**.
- Tests: cada parser contra su fixture, con asserts sobre cantidad de filas, rango de fechas y algunos valores conocidos (cotejados con el boletín).
- `Dockerfile` multi-stage, imagen slim, usuario no root. `docker compose run ingest --source senado` funciona en local.
- **Listo cuando:** en local, con Docker, una corrida baja las 3 fuentes, deja archivos en `./data/raw` y un parquet/CSV de observaciones, y una segunda corrida no duplica nada.

### Fase 2 — Fundación GCP con Terraform · ~1–2 semanas
**Aprendes:** Terraform, IAM, Secret Manager, gestión de costos.
- `infra/bootstrap`: bucket de estado remoto (con versionado), habilitación de APIs, presupuesto con alertas (budget de billing).
- Recursos: buckets (raw con lifecycle hacia Nearline/Coldline), datasets BQ (`raw`, `stg`, `marts`, `ops`) con descripción y labels, Artifact Registry, Secret Manager (el **valor** del secreto se carga a mano con `gcloud`, nunca en Terraform/tfvars), service accounts y bindings de la tabla IAM.
- Separación dev/prod (ver D3).
- Escribir los bindings IAM a mano tú mismo, aunque Claude Code proponga el resto: es lo que se pregunta en entrevistas.
- **Listo cuando:** `terraform destroy && terraform apply` reconstruye todo desde cero sin pasos de consola, salvo cargar el secreto.

### Fase 3 — BigQuery + dbt · ~2 semanas
**Aprendes:** modelado analítico, dbt, calidad de datos, costos de BigQuery.
- `warehouse.py`: carga con *load jobs* desde GCS (parquet), esquema explícito, tabla particionada y clusterizada.
- dbt: `sources.yml` con **freshness** (reemplaza parte de `verificar.py`); staging por fuente; dedupe de vintages; marts.
- Seeds: `dim_serie` (id, nombre, unidad, fuente, frecuencia, `desfase_meses` heredado de `config.yaml` de V1), calendario.
- Tests: `unique`/`not_null`/`relationships`, `accepted_values`, y uno propio `dato_al_dia(desfase_meses)` que reproduce la lógica "dato esperado vs último dato" de V1. Test de atípicos (variación fuera de N desviaciones) como `warn`.
- Lógica de `cifras.py` (KPI y comparaciones) traducida a SQL en marts.
- `dbt docs generate` publicado (artefacto de CI o GitHub Pages).
- **Validación cruzada:** las cifras de `mart_kpi_edicion` para una edición pasada deben coincidir con las publicadas por V1. Es la prueba de que la migración es correcta.
- **Listo cuando:** `dbt build` en dev pasa y los KPI de 2026-09 coinciden con el `contenido_2026-09.yaml` de V1.
- **Pendiente (30-10-2026):** `contenido_2026-09.yaml` no está en la carpeta `/V1`; probablemente vive en Drive (`I:\Mi unidad\...`). Ubicarlo y copiarlo como fixture de referencia antes de la validación cruzada.

### Fase 4 — Despliegue y orquestación · ~1–2 semanas
**Aprendes:** Cloud Run Jobs, Scheduler, Workflows, observabilidad.
- Módulos Terraform `ingest_job`, `dbt_job` (Cloud Run Jobs, cada uno con su SA, timeout, reintentos, límites de CPU/memoria).
- `workflow.yaml`: ingest → dbt freshness → dbt build; manejo de error con log `severity=ERROR`.
- Cloud Scheduler con zona horaria `America/Santiago`.
- Alerta en Cloud Monitoring: política basada en logs de error del workflow/jobs → email.
- Riesgo a vigilar: algunos sitios del Estado bloquean IPs de nubes públicas. Si el INE bloquea Cloud Run, documentarlo en un ADR y evaluar alternativas legítimas (contactar a la fuente, frecuencia menor) antes que evasión.
- **Listo cuando:** el pipeline corre solo una vez programado, y un fallo provocado a propósito genera un correo.

### Fase 5 — CI/CD · ~1 semana
**Aprendes:** GitHub Actions, Workload Identity Federation, flujo de PR.
- `ci.yml` (en cada PR): ruff, pytest, `sqlfluff lint`, `dbt build --target ci` en un dataset efímero por PR, `terraform fmt -check` + `validate` + `plan` comentado en el PR.
- `deploy.yml` (merge a `main`): build y push de imágenes con tag del commit SHA, `terraform apply` en dev; prod con aprobación manual (GitHub Environments).
- Autenticación a GCP solo por WIF, restringida al repositorio y rama.
- Trabajar con ramas y PR aunque estés solo: el historial de PRs es parte del portafolio.
- **Listo cuando:** un cambio de una línea en un modelo dbt llega a prod solo vía PR + aprobación.

### Fase 6 — Consumo (opcional pero recomendable) · ~1 semana
- Dashboard en Looker Studio sobre `marts` (enlace en el README). Gratis y funciona también contra el sandbox.
- Boletín, correo y gráficos quedan fuera de V2 (decidido).

### Fase 7 — Kubernetes (opcional, aprendizaje) · ~1 semana
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
  1. **Fases 0, 1 y 3 se hacen sin tarjeta**: local + Docker + dbt contra BigQuery sandbox.
  2. Se activa la prueba gratuita **recién al empezar la fase 2**, con las fases 2, 4 y 5 planificadas para caber en 90 días.
  3. Por la falta de DML en sandbox: modelos dbt materializados como `table`/`view` (no `incremental` con `merge`),
     y la capa raw se recarga completa desde los archivos con *load jobs* (`WRITE_TRUNCATE`). Los archivos raw son la
     fuente de verdad; BigQuery se puede reconstruir en cualquier momento. Esto además es buena práctica.
  4. Por la expiración de 60 días: nada en BigQuery sandbox es permanente; `make rebuild` debe dejar todo como estaba.
  5. Incrementales con `merge` se introducen en la fase 3b, ya con facturación, como mejora documentada en un ADR.
- Al cerrar la prueba: `terraform destroy` y el repo queda como evidencia (README, capturas, docs de dbt, historial de CI).

### Uso del crédito

- Todo el núcleo (Cloud Run Jobs ocasionales, Scheduler con pocos jobs, Workflows con pocos pasos, BigQuery con MB de datos, GCS con cientos de MB) debería caer en o cerca del nivel gratuito. Verificar en las páginas de precios vigentes antes de la fase 2.
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
3. **Plan primero.** Plan mode en toda tarea no trivial; obligatorio en Terraform, IAM y modelos dbt nuevos.
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
| MCP para BigQuery en fase 3 | No. Claude usa `bq` CLI con tu usuario y tú ves los comandos | Un comando visible es más auditable y enseña la CLI que se usa en el trabajo |
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
| 1 | `test-runner`; fichas de `v1-analista` por fuente del MVP; skill `agregar-fuente` después del 2.º conector; `revisor-convenciones` y worktrees al cierre de la fase |
| 3 | `validador-cifras` (marts vs `contenido_AAAA-MM.yaml` de V1); skill `agregar-serie` |
| 2 | `revisor-iam` (solo lectura). Terraform siempre en plan mode; tú escribes IAM y corres `apply` |
| 4–5 | Revisor de PR antes de cada merge; skill `cerrar-tarea` si el cierre ya se repitió |
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
- **D5 — Idioma del código:** código e identificadores en inglés; documentación de dominio (ADR, fichas de fuentes, plan) en español. Los ids de fuentes y series son datos del dominio y van en español (`snake_case`), igual que los verán GCS y BigQuery (ajuste del 30-10-2026, tarea 0.6).

Abiertas:
- **D1 — Repo público:** recomendado (es el portafolio). Implica sin datos de empresas, sin marca ASIVA, sin credenciales en el historial. Si alguna vez la clave de la API BDE estuvo en un repo, rotarla.
- **D3 — Entornos:** con la prueba gratuita, un solo proyecto GCP con datasets `dev_*`/`prod_*` y Terraform parametrizado por entorno (dos proyectos duplican recursos y consumen crédito sin enseñar mucho más). El README explica cómo sería con dos proyectos.

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
