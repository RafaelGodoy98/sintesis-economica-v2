"""Conector de la API BDE del Banco Central: solo descarga (ADR-0003).

Una consulta GetSeries por serie, con la historia completa desde `first_date` (decisión 1.3: así se
capturan las revisiones; si nada cambió, el archivo es idéntico y el Storage no lo guarda dos veces).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from sintesis_ingest.config import BcentralSource, Settings
from sintesis_ingest.contract import RawFile, SourceError
from sintesis_ingest.http import HttpClient
from sintesis_ingest.parsers.bcentral_api import decode_response

BASE_URL = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
# La UF se publica por adelantado (hasta el día 9 del mes siguiente): se pide un poco más allá de hoy.
LOOKAHEAD_DAYS = 45


class BcentralApiConnector:
    def __init__(self, settings: Settings, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.settings = settings
        self._now = now  # los tests fijan la fecha

    def fetch(self, source: BcentralSource, http: HttpClient) -> list[RawFile]:
        if self.settings.bde_user is None or self.settings.bde_password is None:
            raise SourceError("faltan SINTESIS_BDE_USER y/o SINTESIS_BDE_PASSWORD (ver docs/fuentes.md)")
        credentials = {"user": self.settings.bde_user, "pass": self.settings.bde_password.get_secret_value()}
        last_date: date = self._now().date() + timedelta(days=LOOKAHEAD_DAYS)

        files = []
        for serie_id, code in source.series.items():
            resp = http.get(
                BASE_URL,
                params={
                    "function": "GetSeries",
                    "timeseries": code,
                    "firstdate": source.first_date.isoformat(),
                    "lastdate": last_date.isoformat(),
                },
                secret_params=credentials,  # viajan en la URL, pero HttpClient nunca las muestra
            )
            decode_response(
                resp.content, resp.content_type
            )  # HTTP 200 no basta: si Codigo ≠ 0, SourceError (no se guarda)
            files.append(
                RawFile(
                    source_id=source.id,
                    name=f"{serie_id}.json",
                    content=resp.content,
                    # Completo, con `charset`: lo que declaró el servidor queda registrado y el parser lo usa.
                    media_type=resp.content_type or "application/json",
                    source_url=resp.url,
                    fetched_at=self._now(),
                )
            )
        return files
