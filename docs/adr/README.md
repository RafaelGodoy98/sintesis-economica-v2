# Decisiones de arquitectura (ADR)

Un ADR (*Architecture Decision Record*) registra **una** decisión: qué problema había, qué opciones se consideraron,
qué se decidió y qué consecuencias tiene. Sirve para responder "¿por qué está hecho así?" meses después, sin depender
de la memoria de nadie.

**Reglas del proyecto**
- Claude redacta Contexto y Opciones. **La sección Decisión la escribe Rafael**, con sus palabras.
- Estado: `Propuesta` mientras falta la decisión; `Aceptada` cuando está escrita; `Reemplazada por ADR-NNNN` si cambia.
- Un ADR aceptado no se reescribe: si la decisión cambia, se crea uno nuevo que lo reemplaza.
- Máximo ~1 página. En español (D5).

## Índice

| ADR | Título | Estado |
|---|---|---|
| [0001](0001-elt-gcs-bigquery-dataform.md) | ELT con GCS + BigQuery + Dataform | Aceptada |
| [0002](0002-orquestacion-workflows.md) | Orquestación con Cloud Scheduler + Workflows | Aceptada |
| [0003](0003-conectores-de-ingesta.md) | Ingesta con conectores propios y contrato común | Aceptada |

## Plantilla

```markdown
# ADR-NNNN: <título>

**Estado:** Propuesta · **Fecha:** AAAA-MM-DD

## Contexto
Problema y restricciones que importan para esta decisión.

## Opciones consideradas
### A. <opción>
- A favor: ...
- En contra: ...

## Decisión
_La escribe Rafael._

## Consecuencias
Qué se vuelve más fácil, qué se vuelve más difícil y qué queda pendiente.

## Referencias
```
