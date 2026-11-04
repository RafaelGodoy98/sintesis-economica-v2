"""Almacenamiento raw: guarda cada archivo intacto, una sola vez por contenido (sha256).

Ruta (igual a la que tendrá GCS, docs/plan.md §3):
    <raíz>/source=<source_id>/ingest_date=AAAA-MM-DD/<sha256>_<nombre>
"""

import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sintesis_ingest.contract import RawFile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredFile:
    uri: str
    sha256: str
    size: int
    created: bool  # False = ese contenido ya estaba guardado (en cualquier fecha) y no se escribió nada


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, raw: RawFile, ingest_date: date | None = None) -> StoredFile:
        sha = raw.sha256
        source_dir = self.root / f"source={raw.source_id}"

        # Idempotencia: si el mismo contenido ya existe en CUALQUIER fecha de la fuente,
        # no se vuelve a guardar.
        existing = next(source_dir.glob(f"ingest_date=*/{sha}_*"), None)
        if existing is not None:
            logger.info("ya existía en raw", extra={"uri": existing.as_uri(), "sha256": sha})
            return StoredFile(existing.as_uri(), sha, existing.stat().st_size, created=False)

        day = ingest_date or raw.fetched_at.date()
        target_dir = source_dir / f"ingest_date={day.isoformat()}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{sha}_{raw.name}"

        # Escritura atómica: primero un temporal oculto y luego un rename. Si algo falla a mitad,
        # no queda un archivo incompleto con nombre válido (que la idempotencia tomaría por bueno).
        fd, tmp = tempfile.mkstemp(dir=target_dir, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw.content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

        logger.info(
            "guardado en raw", extra={"uri": target.as_uri(), "sha256": sha, "size": len(raw.content)}
        )
        return StoredFile(target.as_uri(), sha, len(raw.content), created=True)
