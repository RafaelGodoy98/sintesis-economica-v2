# 2026-11-02 — Replanificación: rebanada vertical con el Banco Central

## Contexto
El plan original construía las 3 fuentes del MVP en la fase 1 antes de pasar a BigQuery, Terraform y la nube. Rafael
propone (y Claude recomienda) un **walking skeleton**: una sola fuente de punta a punta y, después, el ensanche.
Motivos: el mayor riesgo (Dataform con el sandbox, ADR-0001) y las competencias menos conocidas (BigQuery, Dataform,
Terraform, IAM, Cloud Run) están en las fases siguientes; un pipeline completo con una fuente vale más en el portafolio;
y el contrato común (ADR-0003) se diseña mejor con una fuente real y se pone a prueba con la segunda.
**Decisiones de Rafael (2026-11-02):** fuente = Banco Central (UF/IMACEC); orden 1 → 3 → 2 → 4 → 5 → ensanche, con renumeración.

## Rama
`docs/replan-rebanada-vertical`, desde `main`. Solo documentación.

## Nueva numeración
| Nueva | Antes | Contenido |
|---|---|---|
| 1 | 1 (recortada) | Ingesta del **Banco Central** (UF/IMACEC) + Docker |
| 2 | 3 | BigQuery + Dataform en sandbox (sin tarjeta); **primera tarea: go/no-go de Dataform** (plan B: dbt) |
| 3 | 2 | GCP con Terraform (**activa la prueba de 90 días**) |
| 4 | 4 | Despliegue y orquestación |
| 5 | 5 | CI/CD |
| 6 | — (nueva) | **Ensanche:** Senado, INE regional (parsers supervisados uno por archivo), 2.ª iteración del INE |
| 7 | 6 | Consumo (opcional) |
| 8 | 7 | Kubernetes (opcional) |

## Cambios
- `docs/plan.md`:
  - §5: reordenar y renumerar las fases. La fase 1 queda solo con el Banco Central; el resto de su contenido pasa a la fase 6.
  - Nota de renumeración (fecha, motivo, tabla antes → ahora).
  - §6: "fases 0, 1 y 2 sin tarjeta; la prueba se activa al empezar la fase 3; las fases 3, 4 y 5 en 90 días; el
    ensanche puede ocurrir después de la prueba, en local y sandbox".
  - §7.4: delegación por fase con la nueva numeración.
  - §8: registrar la decisión.
- `CLAUDE.md`: "BigQuery sandbox hasta la fase 2" → "hasta la fase 3". Una línea.
- `docs/plans/2026-10-30-fase-1.md`: reescribir el tablero (contenido abajo).
- `docs/adr/0001` y `0002`: corregir solo las referencias a números de fase en Contexto y Consecuencias (la Decisión
  no se toca), con una nota "numeración de fases vigente desde 2026-11-02".
- `docs/delegacion.md`: fases de `revisor-iam` (2 → 3), `validador-cifras` y `agregar-serie` (3 → 2), `agregar-fuente` (→ 6).
- Memoria de Claude: los parsers supervisados del INE pasan a la fase 6.

## Tablero nuevo de la fase 1 (Banco Central)
| # | Tarea |
|---|---|
| 1.0 | Verificar el deny de edición sobre V1 (pendiente desde la 0.5) |
| 1.1 | Ficha del Banco Central (`v1-analista`) + códigos UF/IMACEC verificados con `SearchSeries` + credenciales BDE vigentes (revisar D1: rotar si la clave estuvo en un repo) |
| 1.2 | Base común: contrato `Connector`/`RawFile`, cliente HTTP (User-Agent, pausa, reintentos, redacción), `Storage` local idempotente por sha256 |
| 1.3 | Conector + fixture JSON real (sin credenciales) + parser a formato largo `(serie_id, periodo, valor)` + tests |
| 1.4 | CLI `sintesis-ingest run --source <id>` + registro de ejecuciones + `make run-local` |
| 1.5 | `Dockerfile` + `docker compose run ingest` |
| 1.6 | (Opcional) experimento `experiment/dlt-bde` (ADR-0003) |

**Listo cuando:** con Docker, una corrida baja UF e IMACEC, deja el JSON en `./data/raw` y las observaciones en
parquet/CSV, y una segunda corrida no duplica nada.

## Verificación
`make lint`. Releer que no queden números de fase viejos en `plan.md`, CLAUDE.md, los ADR y `delegacion.md`
(un grep de "fase N"), salvo en el registro histórico (Anexo A, planes de tareas cerradas).

## Para que valide Rafael
- La tabla de renumeración y el tablero nuevo de la fase 1.
- Que el ensanche al final (fase 6) y su relación con el fin de la prueba gratuita te parezcan bien.

## Resultado de la verificación
- Hallazgo: `docs/plan.md` ya fijaba el orden de ejecución 0 → 1 → 3 (sandbox) → 2 por el costo. La renumeración hace
  coincidir el número con ese orden.
- Referencias a fases actualizadas en `plan.md` (§2, §3, §4, §5, §6, §7.2, §7.4, §8), CLAUDE.md, ADR 0001/0002 (sin
  tocar las decisiones) y `docs/delegacion.md`. Las menciones a la fase 0 y el Anexo A quedan como registro histórico.
- `make lint` limpio, `make test`: 33 passed.
