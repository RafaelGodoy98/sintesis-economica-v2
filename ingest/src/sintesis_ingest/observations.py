"""Observaciones en CSV: un archivo por archivo raw, nombrado con su sha256.

    <raíz>/source=<source_id>/<sha256>.csv

El nombre sale de la huella del raw: correr dos veces escribe el mismo archivo (no duplica). Para reprocesar
con un parser nuevo basta borrar los CSV: el raw sigue intacto y no hay que volver a pedir nada a la fuente.
Columnas = las de `raw.observaciones` en BigQuery (docs/plan.md §3), salvo `run_id`, que va en el registro de
corridas (si estuviera aquí, cada corrida cambiaría el archivo).
"""

import csv
import os
import tempfile
from datetime import datetime
from pathlib import Path

from sintesis_ingest.contract import Observation

COLUMNS = ["source_id", "series_id", "period", "value", "file_sha256", "file_uri", "ingested_at"]


def csv_path(root: Path, source_id: str, file_sha256: str) -> Path:
    return root / f"source={source_id}" / f"{file_sha256}.csv"


def write_csv(
    path: Path,
    rows: list[Observation],
    *,
    source_id: str,
    file_sha256: str,
    file_uri: str,
    ingested_at: datetime,
) -> None:
    """Escribe el CSV de forma atómica (temporal + rename), como el Storage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".csv")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            for r in rows:
                # str(Decimal) conserva el valor exacto (sin redondeo ni notación científica de float)
                writer.writerow(
                    [
                        source_id,
                        r.series_id,
                        r.period.isoformat(),
                        str(r.value),
                        file_sha256,
                        file_uri,
                        ingested_at.isoformat(),
                    ]
                )
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
