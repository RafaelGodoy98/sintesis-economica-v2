---
name: cerrar-tarea
description: Cierre estándar de una tarea del proyecto (verificación, docs, commits, PR y resumen para Rafael). Rafael la invoca con /cerrar-tarea cuando el trabajo de la tarea está hecho.
disable-model-invocation: true
---

Cierra la tarea actual siguiendo estos pasos en orden. No te saltes ninguno; si uno falla, detente y explícalo.

## 1. Rama
- Confirma que estás en la rama de la tarea, no en `main`. Si estás en `main`, detente y pregunta.

## 2. Qué cambió
- Corre `git status --short`. Cada archivo debe pertenecer a la tarea.
- Si aparece algo inesperado (configuración del editor, cachés, datos), no lo agregues: muéstralo y pregunta.
- Nunca uses `git add -A` ni `git add .`: agrega los archivos por nombre.

## 3. Verificación
- Corre `make lint` y `make test`. Si fallan, corrige y repite antes de seguir.
- Resume el resultado (p. ej. "13 passed, lint limpio"); no pegues logs largos.

## 4. Documentación
- Plan de la tarea en `docs/plans/AAAA-MM-DD-<tarea>.md`, con una sección "Resultado de la verificación" que incluya lo que falló y cómo se resolvió.
- Plan de fase (`docs/plans/*-fase-*.md`): mueve la tarea de "Pendiente" a "Hecho" con una línea.
- `docs/delegacion.md`: suma repeticiones a los candidatos y agrega los patrones nuevos.
- Si la tarea tocó una fuente: actualiza su ficha en `docs/fuentes.md`.
- Si hubo un error que se repitió: propón una regla para `CLAUDE.md`, pero no la escribas sin la aprobación de Rafael.
- Después de editar la documentación, corre `make lint` otra vez: los hooks de formato (fin de archivo, espacios) suelen corregir los `.md` recién editados y harían fallar el commit.

## 5. Commits
- Separa código y documentación cuando ambos cambien: un commit `feat:`/`chore:`/`fix:` y otro `docs:`.
- Mensajes en inglés, con la atribución que indique la sesión.
- Si pre-commit modifica o bloquea el commit, revisa por qué antes de reintentar. Prefiere corregir la causa (configuración) en vez de aceptar el cambio a ciegas.

## 6. Subir y abrir el PR
- Antes de subir, muestra qué se va a enviar: `git log --oneline main..HEAD` y `git diff --stat main`.
- `git push -u origin <rama>` y `gh pr create --base main` con estas secciones: **Qué** (plan y archivos), **Verificación** (resultados reales, incluidas las fallas) y **Para validar (Rafael)** (casillas concretas).
- Nunca hagas merge ni push a `main`: eso lo decide y lo hace Rafael.

## 7. Resumen para Rafael
Termina con un mensaje breve que contenga:
1. **Qué se logró**, en 3–5 líneas de lenguaje simple y sin jerga: qué problema resuelve la tarea, qué se puede hacer
   ahora que antes no, y para qué servirá más adelante en el proyecto. Rafael debe poder explicarlo con sus palabras.
2. **Qué quedó** y el enlace al PR.
3. **Para validar:** diff, cifras o resultados concretos, cada uno con su archivo.
4. **Oportunidades de delegación:** qué hizo o pudo hacer un subagente o skill existente, y qué patrón se repitió (con su conteo en `docs/delegacion.md`).
5. **Comandos para integrar**, descritos por lo que hace cada uno:
   ```bash
   git switch main
   git merge --ff-only <rama>        # main avanza a los commits de la tarea
   git push origin main              # GitHub cierra el PR
   git branch -d <rama> && git push origin --delete <rama>   # borra la rama integrada
   ```
6. **Siguiente tarea** según el plan de fase.
