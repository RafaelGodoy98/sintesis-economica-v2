# Oportunidades de delegación

Registro vivo de candidatos a subagente, skill o hook. Un candidato se crea solo cuando el patrón se repitió 2–3 veces
(docs/plan.md §7.1.6). Claude lo actualiza al cerrar cada tarea; Rafael decide cuándo crear cada uno.
Alimenta `docs/retrospectiva.md` al cierre del proyecto.

| Candidato | Tipo | Para qué | Repeticiones (fecha · tarea) | Estado |
|---|---|---|---|---|
| `v1-analista` | subagente | Leer V1 (solo lectura) y producir la ficha de una fuente | 2026-10-30 · 0.4 (Senado) | Creado |
| `test-runner` | subagente | Correr tests y devolver solo fallas, sin llenar el contexto con logs | — | Planificado fase 1 |
| `agregar-fuente` | skill | Pasos repetibles para sumar un conector (ficha → plan → conector → fixtures → tests) | — | Tras el 2.º conector |
| `revisor-convenciones` | subagente | Revisar un diff contra CLAUDE.md y convenciones del repo | — | Cierre fase 1 |
| `revisor-iam` | subagente | Revisar Terraform/IAM en solo lectura (mínimo privilegio) | — | Fase 2 |
| `validador-cifras` | subagente | Comparar marts contra `contenido_AAAA-MM.yaml` de V1 | — | Fase 3 |
| `agregar-serie` | skill | Sumar una serie a `dim_serie` + tests dbt | — | Fase 3 |
| `cerrar-tarea` | skill | Checklist de cierre (validación, docs, delegación, PR) | 2026-10-30 · 0.4; 0.5; 0.6 | Creado (`.claude/skills/cerrar-tarea/`). Usada en: skill; 0.7 (se agregó "Qué se logró") |
| `v1-analista` sin recarga | aviso | Si la rama activa no tiene el archivo del agente, se descarga; vuelve con *Developer: Reload Window*. En 0.6 se usó Explore | 2026-10-30 · 0.6 | Observando |
| Inspeccionar binarios con un script de librería estándar | patrón | Revisar metadatos y estructura de xlsx/whl sin abrir Excel ni instalar nada | 2026-10-30 · 0.6 (wheel); 0.8 (xlsx) | Observando (2 de 3): candidato a script en `ingest/tests/fixtures/` |
| Falsos positivos de detect-secrets | aviso | Hashes sha256 en manifiestos; se registran en `.secrets.baseline` | 2026-10-30 · 0.8 | Observando |
| `web-fetch` para verificar documentación externa | subagente (incluido) | Comprobar capacidades de una herramienta antes de afirmarlas en un ADR | 2026-10-30 · 0.9 (dlt) | Usado; repetir antes de afirmar precios o límites (fase 2) |
