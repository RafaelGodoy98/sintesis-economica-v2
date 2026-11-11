"""Carga a BigQuery: los CSV de observaciones → `raw.observations` y el registro de corridas → `ops.runs`.

Decisiones (docs/aprendizaje/2.2-carga-bigquery.md):
- Un solo *load job* por tabla, con `WRITE_TRUNCATE`: cada carga reconstruye la tabla completa desde los
  archivos locales (la fuente de verdad). El load job es atómico: entran todas las filas o ninguna.
- Esquema explícito: BigQuery no adivina tipos. `value` es BIGNUMERIC (exacto; NUMERIC no admite los 11
  decimales del Banco Central).
- `raw.observations` va particionada por mes de `ingest_date` y ordenada (cluster) por fuente y serie.
- Nunca se carga una tabla vacía: con `WRITE_TRUNCATE`, cero filas borrarían todo raw.

El cliente de BigQuery se recibe como parámetro: en producción es el real (credenciales ADC); en los tests,
uno falso.
"""

import io
import logging
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from sintesis_ingest import audit, observations
from sintesis_ingest.config import Settings

logger = logging.getLogger(__name__)

OBSERVATIONS_TABLE = "observations"
RUNS_TABLE = "runs"

# El orden es el de las columnas del CSV (observations.COLUMNS): el load job de CSV las asigna por posición.
OBSERVATIONS_SCHEMA = [
    bigquery.SchemaField("source_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("series_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("period", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("value", "BIGNUMERIC", mode="REQUIRED"),
    bigquery.SchemaField("file_sha256", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("raw_path", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("ingest_date", "DATE", mode="REQUIRED"),
]

RUNS_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("started_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("new_files", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("existing_files", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("rows_written", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("duration_s", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("error", "STRING", mode="NULLABLE"),
]


# Datos de referencia (2.3): cada reference/<tabla>.csv va a reference.<tabla>, con su esquema explícito.
# Un CSV que no esté aquí es un error: así nadie sube una tabla con tipos adivinados por BigQuery.
REFERENCE_SCHEMAS = {
    "series": [
        bigquery.SchemaField("series_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("unit", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("frequency", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("seasonally_adjusted", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("expected_lag_months", "INT64", mode="NULLABLE"),
    ],
    # reference_period queda como texto AAAA-MM (como lo escribe una persona); Dataform lo convierte a fecha.
    "release_calendar": [
        bigquery.SchemaField("source_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("reference_period", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("release_date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("notes", "STRING", mode="NULLABLE"),
    ],
}


class LoadError(Exception):
    """La carga no se intentó porque los archivos locales no sirven (vacíos o con columnas inesperadas)."""


def combine_observations(folder: Path) -> tuple[bytes, int]:
    """Junta todos los CSV en uno solo, con un único encabezado. Devuelve (contenido, filas de datos).

    Un load job desde archivo local acepta un solo archivo; por eso se combinan en memoria (son pocos MB).
    """
    header = ",".join(observations.COLUMNS)
    paths = sorted(folder.glob("source=*/*.csv"))
    out = io.StringIO()
    out.write(header + "\n")
    rows = 0
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != header:
            found = lines[0] if lines else "(vacío)"
            raise LoadError(f"{path.name}: columnas inesperadas ({found}); se esperaba {header}")
        data = [line for line in lines[1:] if line]
        out.writelines(line + "\n" for line in data)
        rows += len(data)
    if rows == 0:
        raise LoadError(f"no hay observaciones en {folder}: no se carga (vaciaría raw.{OBSERVATIONS_TABLE})")
    return out.getvalue().encode("utf-8"), rows


def observations_job_config() -> bigquery.LoadJobConfig:
    return bigquery.LoadJobConfig(
        schema=OBSERVATIONS_SCHEMA,
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.MONTH, field="ingest_date"
        ),
        clustering_fields=["source_id", "series_id"],
    )


def runs_job_config() -> bigquery.LoadJobConfig:
    return bigquery.LoadJobConfig(
        schema=RUNS_SCHEMA,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )


def ensure_dataset(client: Any, settings: Settings, dataset_id: str, description: str) -> None:
    dataset = bigquery.Dataset(f"{settings.gcp_project}.{dataset_id}")
    dataset.location = settings.bq_location
    dataset.description = description
    client.create_dataset(dataset, exists_ok=True)  # si ya existe, no lo toca


def _load(
    client: Any, settings: Settings, content: bytes, table_id: str, config: bigquery.LoadJobConfig
) -> int:
    job = client.load_table_from_file(
        io.BytesIO(content), table_id, job_config=config, location=settings.bq_location
    )
    job.result()  # espera y lanza una excepción si BigQuery rechazó la carga
    logger.info(
        "cargado a BigQuery", extra={"table": table_id, "rows": job.output_rows, "job_id": job.job_id}
    )
    return job.output_rows


def read_reference(folder: Path) -> dict[str, bytes]:
    """Lee los CSV de referencia y revisa que cada uno tenga esquema conocido y el encabezado esperado."""
    files = {}
    for path in sorted(folder.glob("*.csv")):
        schema = REFERENCE_SCHEMAS.get(path.stem)
        if schema is None:
            raise LoadError(f"{path.name}: no tiene esquema en REFERENCE_SCHEMAS (warehouse.py)")
        content = path.read_bytes()
        header = content.decode("utf-8").splitlines()[0] if content else ""
        expected = ",".join(f.name for f in schema)
        if header != expected:
            raise LoadError(f"{path.name}: columnas inesperadas ({header}); se esperaba {expected}")
        files[path.stem] = content
    return files


def reference_job_config(table: str) -> bigquery.LoadJobConfig:
    return bigquery.LoadJobConfig(
        schema=REFERENCE_SCHEMAS[table],
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )


def load_all(settings: Settings, client: Any) -> dict[str, int]:
    """Carga observaciones, corridas y datos de referencia. Devuelve las filas cargadas por tabla."""
    data = settings.local_data_dir
    content, rows = combine_observations(data / observations.FOLDER)  # antes de tocar BigQuery
    reference = read_reference(settings.reference_dir)  # también se revisa antes de tocar BigQuery

    ensure_dataset(
        client, settings, settings.bq_raw_dataset, "Observaciones tal como llegaron: todas las ediciones."
    )
    ensure_dataset(client, settings, settings.bq_ops_dataset, "Registro de corridas de la ingesta.")

    loaded = {}
    obs_table = f"{settings.gcp_project}.{settings.bq_raw_dataset}.{OBSERVATIONS_TABLE}"
    loaded[obs_table] = _load(client, settings, content, obs_table, observations_job_config())

    runs_path = data / audit.RUNS_FILE
    if runs_path.exists():
        runs_table = f"{settings.gcp_project}.{settings.bq_ops_dataset}.{RUNS_TABLE}"
        loaded[runs_table] = _load(client, settings, runs_path.read_bytes(), runs_table, runs_job_config())
    else:
        logger.warning("no hay registro de corridas: ops.runs no se carga", extra={"path": str(runs_path)})

    if reference:
        ensure_dataset(
            client, settings, settings.bq_reference_dataset, "Datos mantenidos a mano (reference/)."
        )
    for table, ref_content in reference.items():
        table_id = f"{settings.gcp_project}.{settings.bq_reference_dataset}.{table}"
        loaded[table_id] = _load(client, settings, ref_content, table_id, reference_job_config(table))
    logger.info("carga lista", extra={"observations_rows_in_csv": rows})
    return loaded
