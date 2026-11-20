# Datos de referencia (mantenidos a mano)

Lo que no viene de una fuente sino que escribimos nosotros. Cada `reference/<tabla>.csv` se carga con `make load` a
`reference.<tabla>` en BigQuery, con un esquema explícito (`REFERENCE_SCHEMAS` en
`ingest/src/sintesis_ingest/warehouse.py`). Un CSV nuevo sin esquema detiene la carga: primero se declara su esquema.
`make test` valida estos archivos reales contra sus esquemas.

Guardar siempre como **CSV UTF-8 separado por comas** (en Excel: "CSV UTF-8"; el CSV común de Excel en Windows usa `;`).

## `series.csv`: ficha de cada serie (2.3)

| Columna | Qué va |
|---|---|
| `series_id`, `source_id` | Ids de `sources.yaml` |
| `name`, `unit` | Nombre y unidad para mostrar (`índice 2018=100`, `pesos`) |
| `frequency` | `monthly` o `daily` |
| `seasonally_adjusted` | `true` o `false` |

## `release_calendar.csv`: calendario oficial de publicaciones (2.4)

Una fila por **publicación**. Cada año se **agregan** las filas del año nuevo (el archivo no se reemplaza).
Si el calendario no cubre la fecha actual, `marts.freshness_status` lo marca como `CALENDARIO VENCIDO`.

| Columna | Formato | Qué va | Ejemplo |
|---|---|---|---|
| `source_id` | id de `sources.yaml` | La fuente | `bcentral_imacec` |
| `reference_period` | `AAAA-MM` | El mes **al que corresponde** el dato. Trimestres móviles del INE (empleo): el **último** mes | `2026-09` |
| `release_date` | `AAAA-MM-DD` | El día de publicación, según el calendario oficial | `2026-11-02` |
| `notes` | texto (opcional) | Aclaraciones; sin comas, o entre comillas | `trimestre móvil JAS 2026` |

La UF también lleva calendario: el día 9 de cada mes el Banco Central publica la UF del mes siguiente
(`reference_period` = ese mes siguiente). El Senado no lleva calendario.

## `plausibility_ranges.csv`: rangos de plausibilidad (2.5)

Una fila por **serie y medida**. Si la cifra más reciente queda fuera del rango, `marts.plausibility_status` la marca
`FUERA DE RANGO`: **avisa, no detiene la corrida** (puede ser una crisis real o un error de formato que cambió la
magnitud, p. ej. un separador de miles leído como decimal). Los rangos se calibran contra la historia: deben sonar
solo en crisis reales.

| Columna | Formato | Qué va | Ejemplo |
|---|---|---|---|
| `series_id` | id de `series.csv` | La serie | `imacec_total` |
| `measure` | `var_12m` o `var_month` | Variación en 12 meses o respecto del período anterior | `var_12m` |
| `min_pct`, `max_pct` | número, en % | Límites del rango (incluidos) | `-5`, `10` |
| `notes` | texto (opcional) | Cuándo se calibró y cuándo habría sonado; sin comas, o entre comillas | `calibrado 2026-11: …` |
