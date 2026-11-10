"""`sintesis-ingest run --source <id>`: corre fuentes de punta a punta.
`sintesis-ingest load`: carga a BigQuery.

Por fuente: conector → Storage (raw, solo lo nuevo) → parser → CSV (solo si falta) → registro de corridas.
Una fuente que falla no detiene a las demás (ERROR). Si la corrida no puede empezar, CRITICAL.
Código de salida: 0 todo bien · 1 alguna fuente falló (o la carga a BigQuery falló) · 2 no pudo empezar.
"""

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import ValidationError

from sintesis_ingest import audit, observations
from sintesis_ingest.config import Settings, Source, SourceCatalog, SourcesConfigError, load_sources
from sintesis_ingest.contract import SourceError
from sintesis_ingest.http import HttpClient
from sintesis_ingest.log import configure_logging, log_context, new_run_id, redact, register_secret
from sintesis_ingest.registry import CONNECTORS, PARSERS
from sintesis_ingest.storage import LocalStorage

logger = logging.getLogger(__name__)

EXIT_OK, EXIT_SOURCE_FAILED, EXIT_CANNOT_START = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sintesis-ingest", description="Ingesta de indicadores económicos.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="descarga, guarda en raw y parsea una o más fuentes")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--source", action="append", metavar="ID", help="id de sources.yaml (repetible)")
    which.add_argument("--all", action="store_true", help="todas las fuentes activas")
    sub.add_parser("load", help="carga observaciones y corridas locales a BigQuery (raw y ops)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "load":
        return load()
    try:
        settings = Settings()
        catalog = load_sources()
        sources = select_sources(catalog, args.source, args.all)
    except (ValidationError, SourcesConfigError, ValueError) as e:
        configure_logging("INFO")
        logger.critical("la corrida no puede empezar", extra={"error": str(e)})
        return EXIT_CANNOT_START

    configure_logging(settings.log_level)
    for secret in (settings.bde_user, settings.bde_password and settings.bde_password.get_secret_value()):
        if secret:
            register_secret(secret)  # el censor de logs las conoce desde el primer mensaje
    with HttpClient(settings.contact_email, settings.request_pause_seconds) as http:
        return run(settings, sources, http)


def load() -> int:
    """Carga los archivos locales a BigQuery con credenciales ADC (del usuario o de la cuenta de servicio)."""
    try:
        settings = Settings()
        if not settings.gcp_project:
            raise ValueError("SINTESIS_GCP_PROJECT es obligatoria para `load` (el ID del proyecto de GCP)")
    except (ValidationError, ValueError) as e:
        configure_logging("INFO")
        logger.critical("la carga no puede empezar", extra={"error": str(e)})
        return EXIT_CANNOT_START

    configure_logging(settings.log_level)
    from google.cloud import bigquery  # aquí y no arriba: `run` no necesita cargar la librería de BigQuery

    from sintesis_ingest import warehouse

    try:
        client = bigquery.Client(project=settings.gcp_project, location=settings.bq_location)
        warehouse.load_all(settings, client)
    except warehouse.LoadError as e:
        logger.critical("la carga no puede empezar", extra={"error": str(e)})
        return EXIT_CANNOT_START
    except Exception as e:  # noqa: BLE001 - BigQuery rechazó la carga: la tabla quedó como estaba (atómico)
        logger.error(
            "la carga a BigQuery falló; las tablas quedaron como estaban", extra={"error": redact(str(e))}
        )
        return EXIT_SOURCE_FAILED
    return EXIT_OK


def select_sources(catalog: SourceCatalog, ids: list[str] | None, all_sources: bool) -> list[Source]:
    if all_sources:
        return [s for s in catalog.sources if s.enabled]
    by_id = {s.id: s for s in catalog.sources}
    unknown = [i for i in ids or [] if i not in by_id]
    if unknown:
        raise ValueError(f"id(s) desconocido(s): {', '.join(unknown)}. Válidos: {', '.join(sorted(by_id))}")
    return [by_id[i] for i in ids or []]


def run(settings: Settings, sources: list[Source], http: HttpClient) -> int:
    run_id = new_run_id()
    data = settings.local_data_dir
    storage = LocalStorage(data / "raw")
    with log_context(run_id=run_id):
        logger.info("inicio de corrida", extra={"sources": [s.id for s in sources]})
        records = []
        for source in sources:
            record = run_source(source, settings, http, storage, run_id)
            audit.append(data / audit.RUNS_FILE, record)
            records.append(record)
        failed = [r.source_id for r in records if r.status == "error"]
        logger.info(
            "fin de corrida", extra={"sources_ok": len(records) - len(failed), "sources_failed": failed}
        )
    return EXIT_SOURCE_FAILED if failed else EXIT_OK


def run_source(
    source: Source, settings: Settings, http: HttpClient, storage: LocalStorage, run_id: str
) -> audit.RunRecord:
    started_at = datetime.now(UTC)
    start = time.monotonic()
    new = existing = rows_written = 0
    obs_root = settings.local_data_dir / observations.FOLDER
    error = None
    with log_context(source_id=source.id):
        try:
            if source.connector not in CONNECTORS:
                raise SourceError(f"conector aún no implementado: {source.connector}")
            files = CONNECTORS[source.connector](settings).fetch(source, http)
            for raw in files:
                stored = storage.save(raw)
                new, existing = (new + 1, existing) if stored.created else (new, existing + 1)
                path = observations.csv_path(obs_root, source.id, stored.sha256)
                if path.exists():
                    continue  # ya parseado: segunda corrida sin cambios = cero trabajo
                rows = PARSERS[source.connector](raw, source)
                observations.write_csv(
                    path,
                    rows,
                    source_id=source.id,
                    file_sha256=stored.sha256,
                    raw_path=stored.raw_path,
                    ingest_date=stored.ingest_date,
                )
                rows_written += len(rows)
            logger.info(
                "fuente lista",
                extra={"new_files": new, "existing_files": existing, "rows": rows_written},
            )
        except Exception as e:  # noqa: BLE001 - una fuente que falla no detiene a las demás
            error = f"{type(e).__name__}: {e}"
            logger.error("la fuente falló; su dato no se guardó", extra={"error": error})
    return audit.RunRecord(
        run_id=run_id,
        source_id=source.id,
        started_at=started_at.isoformat(timespec="seconds"),
        status="error" if error else "ok",
        new_files=new,
        existing_files=existing,
        rows=rows_written,
        duration_s=round(time.monotonic() - start, 2),
        error=error,
    )


if __name__ == "__main__":
    sys.exit(main())
