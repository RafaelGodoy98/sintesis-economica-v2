"""Carga a BigQuery sin red: un BigQuery falso anota lo que se le pide (datasets, tablas, configuración y
contenido).

Lo que estos tests NO prueban: que el BigQuery real acepte la carga. Eso se comprueba con la carga real
(tarea 2.2, parte 3) mirando la consola.
"""

import csv
import io
import json
import logging
from pathlib import Path

import pytest
from google.cloud import bigquery

from sintesis_ingest import observations, warehouse
from sintesis_ingest.cli import EXIT_CANNOT_START, main
from sintesis_ingest.config import Settings

HEADER = ",".join(observations.COLUMNS)


class FakeJob:
    def __init__(self, rows: int) -> None:
        self.output_rows = rows
        self.job_id = "job-falso"

    def result(self) -> None:
        return None


class FakeBigQuery:
    """Imita las dos llamadas que usa warehouse.py y guarda todo lo que recibe."""

    def __init__(self) -> None:
        self.datasets: list[bigquery.Dataset] = []
        self.loads: dict[str, dict] = {}

    def create_dataset(self, dataset, exists_ok=False):
        self.datasets.append(dataset)
        return dataset

    def load_table_from_file(self, file_obj, table_id, job_config, location=None):
        content = file_obj.read()
        self.loads[table_id] = {"content": content, "config": job_config, "location": location}
        lines = content.decode("utf-8").splitlines()
        skip = job_config.skip_leading_rows or 0
        return FakeJob(len([line for line in lines[skip:] if line]))


@pytest.fixture
def settings(tmp_path):
    return Settings(
        contact_email="contacto@example.com", local_data_dir=tmp_path / "data", gcp_project="proyecto-prueba"
    )


def write_csv(
    settings: Settings, source: str, name: str, rows: list[list[str]], header: str = HEADER
) -> Path:
    path = settings.local_data_dir / observations.FOLDER / f"source={source}" / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "".join(",".join(r) + "\n" for r in rows), encoding="utf-8")
    return path


def row(series="uf", period="2026-09-01", value="40875.09", sha="a" * 64, source="bcentral_uf"):
    return [
        source,
        series,
        period,
        value,
        sha,
        f"source={source}/ingest_date=2026-11-04/{sha}_x.json",
        "2026-11-04",
    ]


def loaded_rows(fake: FakeBigQuery, table: str) -> list[dict]:
    text = fake.loads[table]["content"].decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


OBS = "proyecto-prueba.raw.observations"
RUNS = "proyecto-prueba.ops.runs"


def test_schema_matches_csv_columns():
    # El contrato entre el CSV (observations.py) y la tabla: mismas columnas, mismo orden (el CSV se carga por
    # posición). Si alguien agrega una columna en un lado y olvida el otro, falla aquí y no en la nube.
    assert [f.name for f in warehouse.OBSERVATIONS_SCHEMA] == observations.COLUMNS


def test_value_is_bignumeric_and_dates_are_dates():
    types = {f.name: f.field_type for f in warehouse.OBSERVATIONS_SCHEMA}
    assert types["value"] == "BIGNUMERIC"  # exacto; NUMERIC rechaza los 11 decimales del Banco Central
    assert (types["period"], types["ingest_date"]) == ("DATE", "DATE")


def test_combines_files_with_a_single_header(settings):
    write_csv(settings, "bcentral_uf", "a", [row(period="2026-09-01")])
    write_csv(settings, "bcentral_imacec", "b", [row(series="imacec_total", source="bcentral_imacec")])
    fake = FakeBigQuery()
    warehouse.load_all(settings, fake)
    text = fake.loads[OBS]["content"].decode("utf-8")
    assert (
        text.count(HEADER) == 1
    )  # si el encabezado de cada archivo entrara, sería una fila con value="value"
    assert {r["series_id"] for r in loaded_rows(fake, OBS)} == {"uf", "imacec_total"}


def test_keeps_every_row_and_exact_values(settings):
    rows = [row(period=f"2026-{m:02d}-01", value=f"97.7304408941{m}") for m in range(1, 10)]
    write_csv(settings, "bcentral_uf", "a", rows)
    fake = FakeBigQuery()
    loaded = warehouse.load_all(settings, fake)
    assert loaded[OBS] == 9
    assert [r["value"] for r in loaded_rows(fake, OBS)] == [
        r[3] for r in rows
    ]  # texto idéntico, sin redondeo


def test_load_replaces_table_partitioned_and_clustered(settings):
    write_csv(settings, "bcentral_uf", "a", [row()])
    fake = FakeBigQuery()
    warehouse.load_all(settings, fake)
    config = fake.loads[OBS]["config"]
    assert (
        config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
    )  # APPEND duplicaría al recargar
    assert (config.time_partitioning.type_, config.time_partitioning.field) == ("MONTH", "ingest_date")
    assert config.clustering_fields == ["source_id", "series_id"]
    assert config.schema == warehouse.OBSERVATIONS_SCHEMA


def test_refuses_to_load_when_there_are_no_observations(settings):
    # WRITE_TRUNCATE con cero filas dejaría raw.observations vacía. Mejor no tocar BigQuery y avisar.
    write_csv(settings, "bcentral_uf", "vacio", [])
    fake = FakeBigQuery()
    with pytest.raises(warehouse.LoadError, match="no hay observaciones"):
        warehouse.load_all(settings, fake)
    assert fake.loads == {} and fake.datasets == []


def test_rejects_csv_with_old_columns(settings):
    # Un CSV de antes de la 2.2 (file_uri, ingested_at) no debe mezclarse con los nuevos: las columnas
    # quedarían cruzadas sin aviso. El error nombra el archivo para poder regenerarlo.
    write_csv(settings, "bcentral_uf", "nuevo", [row()])
    old = HEADER.replace("raw_path", "file_uri").replace("ingest_date", "ingested_at")
    write_csv(settings, "bcentral_uf", "viejo", [row()], header=old)
    fake = FakeBigQuery()
    with pytest.raises(warehouse.LoadError, match="viejo.csv"):
        warehouse.load_all(settings, fake)
    assert fake.loads == {}


def test_runs_load_uses_explicit_schema(settings):
    write_csv(settings, "bcentral_uf", "a", [row()])
    runs = settings.local_data_dir / "ops" / "runs.jsonl"
    runs.parent.mkdir(parents=True)
    record = {"run_id": "r1", "source_id": "bcentral_uf", "started_at": "2026-11-04T01:54:46+00:00"}
    record |= {
        "status": "ok",
        "new_files": 1,
        "existing_files": 0,
        "rows_written": 1,
        "duration_s": 1.5,
        "error": None,
    }
    runs.write_text(json.dumps(record) + "\n", encoding="utf-8")
    fake = FakeBigQuery()
    warehouse.load_all(settings, fake)
    config = fake.loads[RUNS]["config"]
    assert config.schema == warehouse.RUNS_SCHEMA
    assert config.source_format == bigquery.SourceFormat.NEWLINE_DELIMITED_JSON
    assert config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
    assert [f.name for f in warehouse.RUNS_SCHEMA] == list(record)  # mismas claves que escribe audit.py


def test_datasets_are_created_in_us_central1(settings):
    write_csv(settings, "bcentral_uf", "a", [row()])
    fake = FakeBigQuery()
    warehouse.load_all(settings, fake)
    assert [(d.dataset_id, d.location) for d in fake.datasets] == [
        ("raw", "us-central1"),
        ("ops", "us-central1"),
    ]
    assert {load["location"] for load in fake.loads.values()} == {"us-central1"}


def test_missing_runs_file_only_warns(settings, caplog):
    write_csv(settings, "bcentral_uf", "a", [row()])
    fake = FakeBigQuery()
    with caplog.at_level(logging.WARNING):
        warehouse.load_all(settings, fake)
    assert list(fake.loads) == [OBS]
    assert "ops.runs no se carga" in caplog.text


def test_load_without_gcp_project_exits_with_clear_message(monkeypatch, caplog):
    monkeypatch.setenv("SINTESIS_CONTACT_EMAIL", "contacto@example.com")
    monkeypatch.delenv("SINTESIS_GCP_PROJECT", raising=False)
    with caplog.at_level(logging.CRITICAL):
        assert main(["load"]) == EXIT_CANNOT_START
    (record,) = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert "SINTESIS_GCP_PROJECT" in record.error  # el log JSON dice qué variable falta


def test_works_with_default_settings(monkeypatch, tmp_path):
    # Con los valores por defecto de Settings (data relativa, datasets raw/ops, us-central1), como en la
    # corrida real.
    monkeypatch.chdir(tmp_path)
    settings = Settings(contact_email="contacto@example.com", gcp_project="proyecto-prueba")
    write_csv(settings, "bcentral_uf", "a", [row()])
    fake = FakeBigQuery()
    assert warehouse.load_all(settings, fake) == {OBS: 1}
