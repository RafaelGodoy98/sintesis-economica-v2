# 2026-10-30 — Skill `cerrar-tarea`

## Contexto
El cierre de las tareas 0.4, 0.5 y 0.6 repitió los mismos pasos (3 de 3 en `docs/delegacion.md`). En dos de ellas
hubo errores evitables: un archivo del editor (`.vscode/settings.json`) entró al repo por `git add -A`, y un commit
falló porque el lint no se corrió antes. Tarea corta (un archivo de instrucciones), sin plan mode.

## Qué
`.claude/skills/cerrar-tarea/SKILL.md`, con 7 pasos: rama → qué cambió → verificación → documentación → commits → PR → resumen.
- `disable-model-invocation: true`: solo Rafael la activa con `/cerrar-tarea`. Claude no decide cuándo una tarea está cerrada.
- Incluye los dos controles que faltaron: agregar archivos por nombre y correr `make lint` antes de commitear.
- Nunca hace merge ni push a `main`.

## Resultado de la verificación
- La skill apareció como `/cerrar-tarea` tras recargar la ventana y se usó para cerrar esta misma tarea.
- `make lint` limpio, `make test`: 13 passed.
- Hallazgo: la recarga de la ventana reinicia el proceso de Claude Code pero retoma la conversación; recarga agentes,
  skills y CLAUDE.md.
