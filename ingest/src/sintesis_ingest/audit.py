"""Registro de corridas: una línea JSON por fuente y corrida. Solo se agrega, nunca se edita.

Equivalente local de la tabla `ops.ejecuciones` (docs/plan.md §3); reemplaza el `estado_descargas.json` de V1.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sintesis_ingest.log import redact


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    source_id: str
    started_at: str  # ISO 8601, UTC
    estado: Literal["ok", "error"]
    archivos_nuevos: int  # raw guardados en esta corrida
    archivos_existentes: int  # raw que ya estaban (mismo sha256): no se guardaron de nuevo
    filas: int  # observaciones escritas en esta corrida (0 si los CSV ya existían)
    duracion_s: float
    error: str | None = None


def append(path: Path, record: RunRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(record)
    if data["error"]:
        data["error"] = redact(data["error"])  # el mismo censor que los logs
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")
