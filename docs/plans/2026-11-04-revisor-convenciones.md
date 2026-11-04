# 2026-11-04 — Cierre fase 1 (a): subagente `revisor-convenciones`

## Contexto
Quien escribe el código (Claude) también revisaba que cumpliera `CLAUDE.md`, con sesgo de autor. El plan (§7.2)
previó un revisor con ojos frescos para el cierre de la fase 1. Decisiones de Rafael: agente **local** (versionado);
**no** a la 1.6 (dlt).

## Rama
`chore/revisor-convenciones`, desde `main`.

## Decisiones
- `tools: Read, Grep, Glob` (solo lectura por construcción); `model: sonnet`. El diff se le entrega en un archivo.
- Lee `CLAUDE.md` en cada revisión; su lista solo dice *qué buscar* (incluye los avisos de `docs/delegacion.md`).
- Informe fijo: hallazgos (bloquea / sugiere, con `archivo:línea`), reglas sin hallazgos y "No pude verificar".
- `cerrar-tarea`: paso nuevo de revisión antes del PR; `git add -N` antes del lint; integración por squash en GitHub.

## Verificación
Diff sembrado con 6 violaciones (debe encontrarlas todas), diff limpio (sin bloqueos) y el diff real del PR #13.

## Resultado de la verificación
- **Sembrado, 1.ª vuelta:** encontró las 6, pero con líneas del *diff* (corridas en 6) y un identificador en español
  como "sugiere". Se ajustaron sus instrucciones (cómo contar líneas; regla escrita = bloquea).
  **2.ª vuelta:** las 6 + 4 hallazgos legítimos, líneas correctas.
- **Limpio:** sin bloqueos; dos sugerencias razonables.
- **PR #13 real:** hallazgos que Claude no vio. Resultado: **columnas en inglés** (tarea 1.7, decisión de Rafael),
  **plan de una página + resultado breve** (`CLAUDE.md`, decisión de Rafael) y README de fixtures corregido.
- El agente se probó con `Explore` y sus instrucciones; Claude Code lo detectó más tarde en la misma sesión.
- **Primer uso real** (su propia rama): sin bloqueos. Detectó que sus instrucciones contradecían la aclaración nueva de `CLAUDE.md` sobre columnas; corregido.
