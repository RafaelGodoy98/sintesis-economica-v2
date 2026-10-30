# Síntesis Económica V2

Pipeline ELT de indicadores económicos de la Región de Valparaíso y Chile: descarga → GCS (raw) → BigQuery → dbt.
Proyecto de portafolio: debe correr sin intervención de su autor y cada decisión debe poder defenderse.
Plan completo: docs/plan.md. Decisiones: docs/adr/. Fuentes: docs/fuentes.md. Planes por tarea: docs/plans/.

## Forma de trabajo
- Toda tarea no trivial empieza en plan mode. El plan aprobado se guarda en docs/plans/AAAA-MM-DD-<tarea>.md (máximo una página).
- Rafael valida y aprueba; no hacer merge, no correr `terraform apply`, no cambiar IAM sin que él lo pida.
- Bindings IAM y la sección "Decisión" de los ADR los escribe Rafael. Claude puede revisarlos y explicarlos.
- Al cerrar una tarea, listar explícitamente qué debe validar Rafael (diff, cifras, resultados).
- Al cerrar una tarea, incluir "Oportunidades de delegación": qué pudo hacer un subagente/skill existente y qué patrón se repitió. Registrar en docs/delegacion.md; crear uno nuevo solo tras 2–3 repeticiones.
- Explicar el porqué de cada decisión no obvia; Rafael está aprendiendo y debe poder defenderla.

## Reglas
- V1 (/mnt/c/Users/rafae/Workspace Rafael/02_Trabajo/Codes/Sintesis Economica/V1) es solo lectura. No copiar su código: portar con tests.
- Nunca leer ni copiar V1/scripts/core/.env.local.
- Sin rutas absolutas en el código. Toda configuración por variables de entorno (pydantic-settings) o sources.yaml.
- Nunca credenciales en código, tfvars, fixtures ni logs. La API BDE pasa usuario/clave en la URL: no loguear URLs completas.
- Raw es inmutable e idempotente por sha256. Los cálculos (variaciones, KPI) van en dbt, no en Python.
- BigQuery sandbox hasta la fase 2: sin DML; modelos dbt como table/view; raw se recarga con load jobs WRITE_TRUNCATE.
- User-Agent honesto con contacto y pausa entre solicitudes. No evadir bloqueos (WAF) de las fuentes.
- Sin datos de empresas ni marca ASIVA en el repo (fixtures incluidos).

## Comandos
- make test · make lint · make run-local SOURCE=<id> · make dbt-build   (se completan a medida que existan)

## Convenciones
- Código e identificadores en inglés; documentación de dominio en español (D5). Excepción: ids de fuentes y series (datos del dominio) en español, `snake_case` (p. ej. `empleo_regional`, `senado_leyes_publicadas`).
- Commits pequeños, una rama y un PR por tarea.
