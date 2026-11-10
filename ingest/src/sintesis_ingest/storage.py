"""Almacenamiento raw: guarda cada archivo intacto, una sola vez por contenido (sha256).

Ruta (igual a la que tendrá GCS, docs/plan.md §3):
    <raíz>/source=<source_id>/ingest_date=AAAA-MM-DD/<sha256>_<nombre>

`raw_path` es la parte después de <raíz>: la misma en local, en Docker y en la nube (allá se antepone gs://<bucket>/).
`ingest_date` es la fecha del PRIMER guardado: si el mismo contenido vuelve otro día, se conserva la original
(decisiones 3 y 4 de la 2.2, docs/aprendizaje/2.2-carga-bigquery.md).
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
    raw_path: str  # relativa a la raíz de raw, con "/" (p. ej. source=x/ingest_date=2026-11-04/<sha>_x.json)
    ingest_date: date  # fecha del primer guardado de este contenido
    sha256: str
    size: int
    created: bool  # False = ese contenido ya estaba guardado (en cualquier fecha) y no se escribió nada


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _stored(self, path: Path, sha: str, created: bool) -> StoredFile:
        ingest_date = date.fromisoformat(path.parent.name.removeprefix("ingest_date="))
        raw_path = path.relative_to(self.root).as_posix()
        return StoredFile(raw_path, ingest_date, sha, path.stat().st_size, created)

    def save(self, raw: RawFile, ingest_date: date | None = None) -> StoredFile:
        sha = raw.sha256
        source_dir = self.root / f"source={raw.source_id}"

        # Idempotencia: si el mismo contenido ya existe en CUALQUIER fecha de la fuente,
        # no se vuelve a guardar.
        existing = next(source_dir.glob(f"ingest_date=*/{sha}_*"), None)
        if existing is not None:
            stored = self._stored(existing, sha, created=False)
            logger.info("ya existía en raw", extra={"raw_path": stored.raw_path, "sha256": sha})
            return stored

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

        stored = self._stored(target, sha, created=True)
        logger.info(
            "guardado en raw", extra={"raw_path": stored.raw_path, "sha256": sha, "size": stored.size}
        )
        return stored
