"""Contrato común de la ingesta (ADR-0003): un conector solo descarga y entrega `RawFile`.

Guardar (sha256, raw) y parsear son piezas aparte, iguales para todas las fuentes.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from sintesis_ingest.config import Source
from sintesis_ingest.http import HttpClient


@dataclass(frozen=True)
class RawFile:
    """Un archivo tal como lo entregó la fuente, con lo mínimo para rastrear su origen."""

    source_id: str
    name: str  # nombre del archivo, sin carpetas (p. ej. "uf.json")
    content: bytes = field(repr=False)  # repr=False: un print no vuelca megas de bytes
    media_type: str  # el Content-Type declarado, con sus parámetros: "application/json; charset=ISO-8859-1"
    source_url: str  # SIN credenciales (HttpClient la entrega así)
    fetched_at: datetime  # con zona horaria (UTC)

    def __post_init__(self) -> None:
        if not self.name or "/" in self.name or "\\" in self.name or self.name in (".", ".."):
            raise ValueError(f"nombre de archivo inválido: {self.name!r}")
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at debe tener zona horaria (UTC)")

    @property
    def sha256(self) -> str:
        """Huella del contenido. Se calcula, no se guarda: nunca puede quedar desalineada."""
        return hashlib.sha256(self.content).hexdigest()


class SourceError(Exception):
    """La fuente respondió, pero con un error en el contenido (p. ej. HTTP 200 con `Codigo=-5`)."""


@dataclass(frozen=True)
class Observation:
    """Una fila en formato largo: lo que entrega todo parser. Sin cálculos (van en Dataform)."""

    serie_id: str
    periodo: date
    valor: Decimal


class Connector(Protocol):
    """Lo que debe cumplir todo conector: recibir su fuente y el cliente HTTP, devolver archivos.

    Devuelve una lista porque una fuente puede entregar varios archivos (p. ej. xlsx + pdf).
    """

    def fetch(self, source: Source, http: HttpClient) -> list[RawFile]: ...
