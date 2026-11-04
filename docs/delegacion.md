# Oportunidades de delegación

Registro vivo de candidatos a subagente, skill o hook. Un candidato se crea solo cuando el patrón se repitió 2–3 veces
(docs/plan.md §7.1.6). Claude lo actualiza al cerrar cada tarea; Rafael decide cuándo crear cada uno.
Alimenta `docs/retrospectiva.md` al cierre del proyecto.

| Candidato | Tipo | Para qué | Repeticiones (fecha · tarea) | Estado |
|---|---|---|---|---|
| `v1-analista` | subagente | Leer V1 (solo lectura) y producir la ficha de una fuente | 2026-10-30 · 0.4 (Senado); 2026-11-03 · 1.1 (Banco Central) | Creado |
| `test-runner` | subagente | Correr tests y devolver solo fallas, sin llenar el contexto con logs | — (1.2: 59 tests, salida corta; aún no hizo falta) | Planificado fase 1; crear cuando los logs de tests crezcan (1.3–1.5) |
| `agregar-fuente` | skill | Pasos repetibles para sumar un conector (ficha → plan → conector → fixtures → tests) | — | Fase 6, tras el 2.º conector nuevo |
| `revisor-convenciones` | subagente | Revisar un diff contra CLAUDE.md y convenciones del repo | 2026-11-04 · cierre fase 1 (sembrado, limpio, PR #13, su propia rama) | **Creado** (`.claude/agents/`), local por decisión de Rafael. Integrado a `cerrar-tarea` (paso 6). Idea futura: versión genérica global con `configurar-repo` |
| `revisor-iam` | subagente | Revisar Terraform/IAM en solo lectura (mínimo privilegio) | — | Fase 3 |
| `validador-cifras` | subagente | Comparar marts contra `contenido_AAAA-MM.yaml` de V1 | — | Fase 2 |
| `agregar-serie` | skill | Sumar una serie a `dim_serie` + assertions de Dataform | — | Fase 2 |
| `cerrar-tarea` | skill | Checklist de cierre (validación, docs, delegación, PR) | 2026-10-30 · 0.4; 0.5; 0.6 | Creado (`.claude/skills/cerrar-tarea/`). Usada en: skill; 0.7 (se agregó "Qué se logró"); 0.8; 0.9; replan; 1.0; 1.1a; 1.1; 1.2; 1.3; 1.4; 1.5; revisor |
| `v1-analista` sin recarga | aviso | Si la rama activa no tiene el archivo del agente, se descarga; vuelve con *Developer: Reload Window*. En 0.6 se usó Explore | 2026-10-30 · 0.6 | Observando |
| Inspeccionar binarios con un script de librería estándar | patrón | Revisar metadatos y estructura de xlsx/whl sin abrir Excel ni instalar nada | 2026-10-30 · 0.6 (wheel); 0.8 (xlsx) | Observando (2 de 3): candidato a script en `ingest/tests/fixtures/` |
| Falsos positivos de detect-secrets | aviso | Hashes sha256 en manifiestos; se registran en `.secrets.baseline` | 2026-10-30 · 0.8; 2026-11-03 · 1.3 | Observando |
| `web-fetch` para verificar documentación externa | subagente (incluido) | Comprobar capacidades de una herramienta antes de afirmarlas en un ADR | 2026-10-30 · 0.9 (dlt); 2026-11-03 · 1.1a (sandbox) | Usado 2 veces; repetir antes de afirmar precios o límites (fase 3) |
| `configurar-repo` | skill de usuario (`~/.claude/skills/`) | Preguntar preferencias una vez y armar un repo nuevo (uv, ruff, pytest, pre-commit, Makefile, README, .gitignore, .env y secretos, ¿sandbox?) | Fase 0 completa (0.2, 0.5, 0.6, 1.1a) | Pedido por Rafael el 2026-11-03; se arma al final de la sesión |
| Spike de API con credenciales del usuario | patrón | Script desechable en el scratchpad que lee `.env` con `Settings`, nunca imprime URL ni excepciones, guarda el raw; Rafael lo corre con `!` y Claude analiza sin conexión | 2026-11-03 · 1.1 (dos rondas); 1.3 (fixtures, con `HttpClient`) | Observando (2 de 3): candidato a skill al sumar otra API con credenciales. **Condición:** solo si la respuesta no es sensible; si lo es, se analiza en la máquina de Rafael y Claude ve solo agregados (pedido de Rafael) |
| Tests que buscan credenciales en logs y errores | patrón | Cada pieza que toca credenciales tiene un test que falla si aparecen en logs, URL devuelta o mensaje de error. En la 1.2 encontró la fuga de httpx | 2026-11-03 · 1.1a (Settings); 1.2 (HttpClient) | **Resuelto en la 1.3 con un mecanismo:** el canario (`ingest/tests/conftest.py`) vigila todos los tests; ya no hace falta un test por pieza |
| Herramientas que alteran fixtures | aviso | `end-of-file-fixer` agregó un salto de línea y `.gitattributes` (`text=auto`) convirtió CRLF → LF en los JSON de la API: ambos cambian su sha256. En local los tests pasaban; en un clon nuevo habrían fallado | 2026-11-03 · 1.3 | Resuelto: fixtures fuera de esos hooks y `-text` en `.gitattributes`. Verificar con `git cat-file` el hash de lo guardado |
| Probar con la configuración por defecto | aviso | Los tests usaban rutas absolutas (`tmp_path`); la corrida real usa `data` (relativa) y falló en `as_uri()`. Al menos un test por pieza debe correr con los valores por defecto de `Settings` | 2026-11-04 · 1.4 | Observando (1 de 3) |
| Hacer fallar a propósito cada test de una barrera | patrón | Comprobar que el test detecta lo que dice: canario (1.3, encontró que nunca sonaba), ruta relativa (1.4), `USER appuser` (1.5) | 2026-11-03 · 1.3; 2026-11-04 · 1.4; 1.5 | **Regla en `CLAUDE.md`** (aprobada por Rafael, 2026-11-04) |
