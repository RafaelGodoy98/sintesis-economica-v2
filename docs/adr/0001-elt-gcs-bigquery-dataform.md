# ADR-0001: ELT con GCS + BigQuery + Dataform

**Estado:** Aceptada · **Fecha:** 2026-10-30

> Números de fase según la numeración vigente desde 2026-11-02 (`docs/plan.md` §5).

## Contexto
V1 transformaba los datos en Power Query, dentro de un Excel de escritorio, y calculaba los KPI en Python. Nada de eso
corre sin una persona ni se puede auditar. V2 necesita decidir **dónde se guardan los datos y dónde se transforman**.

Restricciones:
- **Escala:** ≈ 10 fuentes, archivos de KB, una corrida mensual. El volumen no es el problema; la trazabilidad sí.
- **Revisiones:** el INE y el Banco Central corrigen cifras; hay que poder reconstruir qué se publicó en cada edición (*vintages*).
- **Costo:** sin gasto. BigQuery sandbox hasta la fase 3 (sin DML, tablas que expiran a los 60 días) y prueba gratuita de 90 días después.
- **Portafolio:** las herramientas deben ser reconocibles en el mercado laboral de ingeniería de datos.
- Regla de CLAUDE.md: raw inmutable por sha256; los cálculos van en SQL, no en Python.

## Opciones consideradas
### A. ETL en Python: descargar, transformar con pandas y cargar tablas finales
- A favor: un solo lenguaje; es lo más parecido a V1.
- En contra: si cambia un cálculo hay que volver a descargar; no queda el archivo original para auditar ni reconstruir
  vintages; tests y linaje hay que construirlos a mano; contradice la regla "cálculos en SQL".

### B. ELT: archivo original a GCS → tablas raw en BigQuery → transformación con dbt
- A favor: el archivo original queda guardado (inmutable, por sha256) y BigQuery se puede reconstruir desde ahí; dbt
  da tests de datos, documentación y linaje; funciona en sandbox con modelos `table`/`view`; dbt + BigQuery es una
  combinación muy demandada.
- En contra: dos herramientas más que aprender (dbt y BigQuery); el sandbox obliga a recargar raw completo
  (`WRITE_TRUNCATE`) y a no usar incrementales hasta después de la fase 3.

### C. Igual que B, pero con Dataform en vez de dbt
- A favor: es nativo de GCP, viene integrado en la consola de BigQuery y no requiere otro contenedor ni otro job.
- En contra: amarra la transformación a GCP; comunidad y presencia en ofertas de empleo menores que dbt.

### D. Postgres gestionado (Cloud SQL) + dbt
- A favor: SQL estándar; Postgres es conocido.
- En contra: una instancia encendida tiene costo fijo por hora, aunque se use una vez al mes; no está disponible en sandbox;
  a esta escala no aporta frente a un warehouse serverless.

### E. DuckDB local (+ dbt-duckdb)
- A favor: gratis, rápido y muy simple para datos chicos.
- En contra: no demuestra una arquitectura en la nube (objetivo del portafolio); compartir los datos o conectar un
  dashboard exige montar algo más; no corre "sin su autor" salvo que se aloje en algún lado.

## Decisión
_Utilizar opción C. BigQuery + Dataform, dado que el objetivo de proyecto es utilizar entorno BigQuery y es más limpio utilizar su función nativa. Acepto que probablemente sea menos popular que dbt pero garantizará demostrar capacidad de implementar proyectos en GCP limpios._

## Consecuencias
- **Se mantiene "raw primero":** el archivo original va a GCS y BigQuery se reconstruye desde ahí. La decisión solo
  cambia la herramienta de transformación.
- **La transformación se escribe en SQLX** dentro de un repositorio de Dataform conectado a GitHub. Los tests de datos
  son *assertions* y el linaje se ve en la consola de BigQuery.
- **Desaparece el job "dbt" en Cloud Run:** Workflows (ADR-0002) invoca a Dataform directamente. El mecanismo se define en la fase 4.
- **Verificado en la tarea 2.1 (2026-11-04): GO.** Con la CLI local (`@dataform/cli` 3.1.2, ADC, us-central1) contra el
  sandbox: `compile`, `run` (vista y tabla), 2.ª corrida sin duplicados, assertions que pasan y una sembrada que corta la
  corrida (salida 1). Límites: `incremental` falla desde la 2.ª corrida (DML) → solo `table`/`view` hasta la fase 3;
  Cloud Storage exige facturación → carga local hasta la fase 3. Se desarrolla y prueba en local sin repositorio en GCP;
  el repositorio administrado (cuenta de servicio propia + IAM, modo *strict act-as*) llega en la fase 3/4.
  El plan B (dbt) no fue necesario. Plan: `docs/plans/2026-11-04-2.1-dataform-go-no-go.md`.
- Referencias a dbt en `docs/plan.md` (fases 2 y 5): actualizadas en la 2.1 (`CLAUDE.md` ya no tenía). Quedan solo las históricas
  (borrador de CLAUDE.md en el §7 y tabla de la fase 0).

## Referencias
- `docs/plan.md` §2 (objetivo), §3 (capas de datos y vintages), §6 (sandbox).
- BigQuery sandbox: https://cloud.google.com/bigquery/docs/sandbox
- Precios de BigQuery: https://cloud.google.com/bigquery/pricing
- dbt: https://docs.getdbt.com · Dataform: https://cloud.google.com/dataform/docs
