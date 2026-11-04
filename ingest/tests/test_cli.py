"""El CLI de punta a punta, con un servidor simulado y las respuestas reales de la 1.3 (sin internet)."""

import csv
import json
import logging
from pathlib import Path

import httpx
import pytest

from sintesis_ingest.cli import EXIT_CANNOT_START, EXIT_OK, EXIT_SOURCE_FAILED, main, run, select_sources
from sintesis_ingest.config import Settings, load_sources
from sintesis_ingest.http import HttpClient

FIXTURES = Path(__file__).parent / "fixtures" / "bcentral"
IMACEC = (FIXTURES / "bcentral_imacec_imacec_total_2026-09.json").read_bytes()
UF = (FIXTURES / "bcentral_uf_uf_2026-10.json").read_bytes()


def fake_bde(request: httpx.Request) -> httpx.Response:
    """Responde la UF o el IMACEC total (a las otras series del IMACEC, la misma respuesta con su código)."""
    code = request.url.params["timeseries"]
    if code.startswith("F073"):
        body = UF
    else:
        data = json.loads(IMACEC.decode("cp1252"))
        data["Series"]["seriesId"] = code
        body = json.dumps(data, ensure_ascii=False).encode("cp1252")
    return httpx.Response(200, content=body, headers={"content-type": "application/json; charset=ISO-8859-1"})


@pytest.fixture
def settings(tmp_path):
    return Settings(contact_email="contacto@example.com", local_data_dir=tmp_path / "data")


def run_ids(settings, *ids):
    sources = select_sources(load_sources(), list(ids), all_sources=False)
    http = HttpClient(
        "contacto@example.com", 0, transport=httpx.MockTransport(fake_bde), sleep=lambda s: None
    )
    return run(settings, sources, http)


def files_under(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*") if p.is_file()) if path.exists() else []


def audit_lines(settings) -> list[dict]:
    path = settings.local_data_dir / "ops" / "ejecuciones.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_run_leaves_raw_csv_and_audit_line(settings):
    assert run_ids(settings, "bcentral_imacec") == EXIT_OK
    data = settings.local_data_dir
    assert len(files_under(data / "raw" / "source=bcentral_imacec")) == 10
    assert len(files_under(data / "observaciones" / "source=bcentral_imacec")) == 10
    (record,) = audit_lines(settings)
    assert record["source_id"] == "bcentral_imacec"
    assert (record["status"], record["new_files"], record["rows"]) == ("ok", 10, 3690)
    assert record["error"] is None


def test_second_run_creates_nothing_new(settings):
    run_ids(settings, "bcentral_uf")
    before = files_under(settings.local_data_dir / "raw") + files_under(
        settings.local_data_dir / "observaciones"
    )
    assert run_ids(settings, "bcentral_uf") == EXIT_OK
    after = files_under(settings.local_data_dir / "raw") + files_under(
        settings.local_data_dir / "observaciones"
    )
    assert after == before
    first, second = audit_lines(settings)
    assert (second["new_files"], second["existing_files"], second["rows"]) == (0, 1, 0)
    assert first["run_id"] != second["run_id"]


def test_csv_has_exact_values_and_traceability(settings):
    run_ids(settings, "bcentral_uf")
    (path,) = files_under(settings.local_data_dir / "observaciones")
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 31
    assert rows[0]["series_id"] == "uf"
    assert (rows[0]["period"], rows[0]["value"]) == ("2026-10-01", "41065.38")  # exacto, sin redondeo
    (raw,) = files_under(settings.local_data_dir / "raw")
    assert rows[0]["file_sha256"] == path.stem and raw.name.startswith(path.stem)
    assert rows[0]["file_uri"] == raw.as_uri()


def test_failing_source_does_not_stop_the_others(settings, caplog):
    # senado_leyes_publicadas aún no tiene conector (fase 6)
    with caplog.at_level(logging.ERROR):
        code = run_ids(settings, "bcentral_uf", "senado_leyes_publicadas", "bcentral_imacec")
    assert code == EXIT_SOURCE_FAILED
    statuses = {r["source_id"]: r["status"] for r in audit_lines(settings)}
    assert statuses == {"bcentral_uf": "ok", "senado_leyes_publicadas": "error", "bcentral_imacec": "ok"}
    (failed,) = [r for r in audit_lines(settings) if r["status"] == "error"]
    assert "conector aún no implementado" in failed["error"]
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_a_source_error_never_writes_credentials_to_the_audit(settings, canary):
    def bad(request):
        return httpx.Response(
            200, content=(FIXTURES / "bcentral_uf_credenciales_invalidas.json").read_bytes()
        )

    http = HttpClient("contacto@example.com", 0, transport=httpx.MockTransport(bad), sleep=lambda s: None)
    sources = select_sources(load_sources(), ["bcentral_uf"], all_sources=False)
    assert run(settings, sources, http) == EXIT_SOURCE_FAILED
    text = (settings.local_data_dir / "ops" / "ejecuciones.jsonl").read_text(encoding="utf-8")
    assert "Invalid username or password" in text
    assert canary["password"] not in text and canary["user"] not in text


# --- main(): la corrida no puede empezar ---


def test_without_contact_email_the_run_does_not_start(monkeypatch, caplog):
    monkeypatch.delenv("SINTESIS_CONTACT_EMAIL", raising=False)
    with caplog.at_level(logging.CRITICAL):
        assert main(["run", "--source", "bcentral_uf"]) == EXIT_CANNOT_START
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_unknown_source_id_is_a_clear_error(monkeypatch, caplog):
    monkeypatch.setenv("SINTESIS_CONTACT_EMAIL", "contacto@example.com")
    with caplog.at_level(logging.CRITICAL):
        assert main(["run", "--source", "no_existe"]) == EXIT_CANNOT_START
    (record,) = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert "no_existe" in record.error and "bcentral_uf" in record.error  # dice cuáles son válidos


def test_all_selects_only_enabled_sources():
    ids = [s.id for s in select_sources(load_sources(), None, all_sources=True)]
    assert "bcentral_uf" in ids and "bcentral_imacec" in ids


def test_source_and_all_cannot_be_combined():
    with pytest.raises(SystemExit):
        main(["run", "--source", "bcentral_uf", "--all"])


def test_run_with_default_relative_data_dir(monkeypatch):
    # Reproduce la primera corrida real: local_data_dir por defecto ("data", relativa al directorio actual).
    settings = Settings(contact_email="contacto@example.com")
    assert not settings.local_data_dir.is_absolute()
    assert run_ids(settings, "bcentral_uf") == EXIT_OK
    assert run_ids(settings, "bcentral_uf") == EXIT_OK
