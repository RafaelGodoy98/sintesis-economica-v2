"""Conector y parser de la API BDE, contra respuestas reales guardadas (fixtures/bcentral)."""

import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from sintesis_ingest.config import BcentralSource, Settings, load_sources
from sintesis_ingest.connectors.bcentral_api import BcentralApiConnector
from sintesis_ingest.contract import SourceError
from sintesis_ingest.http import HttpClient
from sintesis_ingest.parsers.bcentral_api import encoding_for, parse

FIXTURES = Path(__file__).parent / "fixtures" / "bcentral"
IMACEC = (FIXTURES / "bcentral_imacec_imacec_total_2026-09.json").read_bytes()
UF = (FIXTURES / "bcentral_uf_uf_2026-10.json").read_bytes()
BAD_CREDENTIALS = (FIXTURES / "bcentral_uf_credenciales_invalidas.json").read_bytes()
IMACEC_SERIES = {"imacec_total": "F032.IMC.IND.Z.Z.EP18.Z.Z.0.M"}
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def catalog_source(source_id: str) -> BcentralSource:
    return next(s for s in load_sources().sources if s.id == source_id)


# --- parser ---


def test_parser_reads_full_imacec_history():
    rows = parse(IMACEC, IMACEC_SERIES)
    assert len(rows) == 369
    assert rows[0].series_id == "imacec_total"
    assert (rows[0].period, rows[0].value) == (date(1996, 1, 1), Decimal("42.487431369417"))
    assert (rows[-1].period, rows[-1].value) == (date(2026, 9, 1), Decimal("110.045265996356"))


def test_parser_reads_daily_uf():
    rows = parse(UF, {"uf": "F073.UFF.PRE.Z.D"})
    assert len(rows) == 31
    assert (rows[0].period, rows[0].value) == (date(2026, 10, 1), Decimal("41065.38"))


def test_values_are_exact_decimals_not_floats():
    (row, *_) = parse(UF, {"uf": "F073.UFF.PRE.Z.D"})
    assert isinstance(row.value, Decimal)


def test_cp1252_accents_are_read():
    # el fixture del IMACEC trae "índice" con el byte 0xED: en UTF-8 fallaría
    assert "\xed".encode("cp1252") in IMACEC
    parse(IMACEC, IMACEC_SERIES)  # no lanza


def test_api_error_with_http_200_is_a_clear_error():
    with pytest.raises(SourceError, match="Codigo=-5: Invalid username or password"):
        parse(BAD_CREDENTIALS, {"uf": "F073.UFF.PRE.Z.D"})


def test_unknown_series_code_is_an_error():
    with pytest.raises(SourceError, match="no está en la configuración"):
        parse(IMACEC, {"uf": "F073.UFF.PRE.Z.D"})


def with_obs(*obs) -> bytes:
    data = json.loads(UF.decode("cp1252"))
    data["Series"]["Obs"] = list(obs)
    return json.dumps(data).encode("cp1252")


def test_row_with_status_other_than_ok_is_excluded_and_warned(caplog):
    content = with_obs(
        {"indexDateString": "01-10-2026", "value": "41065.38", "statusCode": "OK"},
        {"indexDateString": "02-10-2026", "value": "NaN", "statusCode": "ND"},
    )
    with caplog.at_level(logging.WARNING):
        rows = parse(content, {"uf": "F073.UFF.PRE.Z.D"})
    assert [r.period for r in rows] == [date(2026, 10, 1)]
    (warning,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning.count == 1 and warning.examples == ["02-10-2026=ND"]


def test_unexpected_date_format_fails_instead_of_guessing():
    content = with_obs({"indexDateString": "2026-10-01", "value": "1.0", "statusCode": "OK"})
    with pytest.raises(SourceError, match="formato inesperado"):
        parse(content, {"uf": "F073.UFF.PRE.Z.D"})


def test_non_numeric_value_with_ok_status_fails():
    content = with_obs({"indexDateString": "01-10-2026", "value": "NaN", "statusCode": "OK"})
    with pytest.raises(SourceError, match="no numérico"):
        parse(content, {"uf": "F073.UFF.PRE.Z.D"})


# --- conector ---


class FakeBde:
    """Simula la API: responde el fixture que corresponde al código pedido y anota cada solicitud."""

    def __init__(self, body: bytes | None = None):
        self.body = body
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = self.body or (UF if "F073" in str(request.url) else IMACEC)
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json; charset=ISO-8859-1"}
        )


def run_connector(source_id: str, server: FakeBde, settings: Settings | None = None):
    settings = settings or Settings(
        contact_email="contacto@example.com"
    )  # credenciales: el canario (conftest)
    http = HttpClient(settings.contact_email, 0, transport=httpx.MockTransport(server), sleep=lambda s: None)
    return BcentralApiConnector(settings, now=lambda: NOW).fetch(catalog_source(source_id), http)


def test_connector_asks_each_series_with_full_history():
    server = FakeBde()
    files = run_connector("bcentral_imacec", server)
    assert len(server.requests) == len(files) == 10
    first = server.requests[0].url.params
    assert first["function"] == "GetSeries"
    assert first["timeseries"] == "F032.IMC.IND.Z.Z.EP18.Z.Z.0.M"
    assert first["firstdate"] == "1996-01-01"
    assert first["lastdate"] == "2026-12-18"  # hoy + 45 días: alcanza la UF publicada por adelantado


def test_connector_sends_at_sign_literally(canary):
    server = FakeBde()
    run_connector("bcentral_uf", server)
    assert f"user={canary['user']}" in server.requests[0].url.raw_path.decode()


def test_connector_delivers_raw_file_without_credentials(canary):
    (raw,) = run_connector("bcentral_uf", FakeBde())
    assert (raw.source_id, raw.name) == ("bcentral_uf", "uf.json")
    assert raw.media_type == "application/json; charset=ISO-8859-1"  # lo declarado queda registrado
    assert raw.content == UF  # tal cual llegó
    assert raw.fetched_at == NOW
    assert canary["password"] not in raw.source_url and canary["user"] not in raw.source_url


def test_connector_turns_api_error_into_clear_error_without_credentials(canary):
    with pytest.raises(SourceError) as exc:
        run_connector("bcentral_uf", FakeBde(body=BAD_CREDENTIALS))
    assert "Invalid username or password" in str(exc.value)
    assert canary["password"] not in str(exc.value) and canary["user"] not in str(exc.value)


def test_connector_says_when_credentials_are_missing(monkeypatch):
    monkeypatch.delenv("SINTESIS_BDE_PASSWORD")
    settings = Settings(contact_email="contacto@example.com")
    with pytest.raises(SourceError, match="SINTESIS_BDE_PASSWORD"):
        run_connector("bcentral_uf", FakeBde(), settings)


def test_end_to_end_parse_of_connector_output():
    (raw,) = run_connector("bcentral_uf", FakeBde())
    rows = parse(raw.content, catalog_source("bcentral_uf").series, raw.media_type)
    assert {r.series_id for r in rows} == {"uf"}


# --- codificación declarada (regla WHATWG) ---


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("application/json; charset=ISO-8859-1", "cp1252"),  # lo que declara hoy la API BDE
        ("application/json; charset=utf-8", "utf-8"),
        ('application/json; charset="UTF-8"', "utf-8"),
        ("application/json", "cp1252"),  # sin declaración: lo verificado
        (None, "cp1252"),
    ],
)
def test_declared_charset_is_respected_with_whatwg_rule(content_type, expected):
    assert encoding_for(content_type) == expected


def test_parser_follows_declared_utf8_if_the_source_changes():
    utf8 = IMACEC.decode("cp1252").encode(
        "utf-8"
    )  # misma respuesta, como si el Banco Central cambiara a UTF-8
    rows = parse(utf8, IMACEC_SERIES, "application/json; charset=utf-8")
    assert len(rows) == 369


def test_unknown_declared_charset_falls_back_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        assert encoding_for("application/json; charset=x-inventada") == "cp1252"
    assert any(r.levelno == logging.WARNING for r in caplog.records)
