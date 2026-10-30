import io
import json
import logging

import pytest

from sintesis_ingest.log import configure_logging, log_context, new_run_id, redact

logger = logging.getLogger("sintesis_ingest.test")


@pytest.fixture
def log_buffer():
    buffer = io.StringIO()
    configure_logging("DEBUG", stream=buffer)
    return buffer


@pytest.fixture
def log_lines(log_buffer):
    """Devuelve una función que lee las líneas emitidas (y aún no leídas) como dicts."""

    def read() -> list[dict]:
        out = log_buffer.getvalue()
        log_buffer.seek(0)
        log_buffer.truncate()
        return [json.loads(line) for line in out.splitlines()]

    return read


def test_each_line_is_json_with_base_fields(log_lines):
    logger.info("descarga lista")
    (line,) = log_lines()
    assert line["message"] == "descarga lista"
    assert line["severity"] == "INFO"
    assert line["logger"] == "sintesis_ingest.test"
    assert line["timestamp"].endswith("+00:00")


def test_severity_follows_level(log_lines):
    logger.warning("cero filas")
    assert log_lines()[0]["severity"] == "WARNING"


def test_context_fields_only_inside_block(log_lines):
    with log_context(run_id="r1", source_id="empleo_regional"):
        logger.info("dentro")
    logger.info("fuera")
    inside, outside = log_lines()
    assert (inside["run_id"], inside["source_id"]) == ("r1", "empleo_regional")
    assert "run_id" not in outside
    assert "source_id" not in outside


def test_nested_context_adds_source_to_run(log_lines):
    with log_context(run_id="r1"):
        with log_context(source_id="senado_leyes_publicadas"):
            logger.info("fuente")
        logger.info("corrida")
    source_line, run_line = log_lines()
    assert source_line["run_id"] == "r1"
    assert source_line["source_id"] == "senado_leyes_publicadas"
    assert run_line == {**run_line, "run_id": "r1"}
    assert "source_id" not in run_line


def test_extra_fields_are_included(log_lines):
    logger.info("guardado", extra={"rows": 42, "sha256": "abc"})
    line = log_lines()[0]
    assert (line["rows"], line["sha256"]) == (42, "abc")


def test_exception_stays_in_the_same_line(log_lines):
    try:
        raise ValueError("html inesperado")
    except ValueError:
        logger.exception("falló el parseo")
    (line,) = log_lines()
    assert line["severity"] == "ERROR"
    assert "ValueError: html inesperado" in line["exception"]


def test_credentials_in_urls_are_redacted(log_lines):
    logger.error("falló https://si3.bcentral.cl/api?user=rafa@mail.cl&pass=s3cr3t&timeseries=F073")
    message = log_lines()[0]["message"]
    assert "s3cr3t" not in message
    assert "rafa@mail.cl" not in message
    assert "user=***&pass=***&timeseries=F073" in message


def test_redact_keeps_unrelated_params():
    assert redact("?region=5&monkey=1&api_key=xyz") == "?region=5&monkey=1&api_key=***"


def test_configure_twice_does_not_duplicate_lines(log_buffer, log_lines):
    configure_logging("INFO", stream=log_buffer)
    logger.info("una vez")
    assert len(log_lines()) == 1


def test_level_filters_lower_severities(log_buffer, log_lines):
    configure_logging("WARNING", stream=log_buffer)
    logger.info("no aparece")
    logger.warning("aparece")
    assert [line["message"] for line in log_lines()] == ["aparece"]


def test_run_ids_are_unique():
    assert new_run_id() != new_run_id()
