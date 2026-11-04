"""Qué conector y qué parser usa cada tipo de fuente (`connector` en sources.yaml).

Agregar una fuente nueva = una entrada en cada diccionario (fase 6: INE y Senado).
"""

from collections.abc import Callable

from sintesis_ingest.config import Settings, Source
from sintesis_ingest.connectors.bcentral_api import BcentralApiConnector
from sintesis_ingest.contract import Connector, Observation, RawFile
from sintesis_ingest.parsers import bcentral_api

CONNECTORS: dict[str, Callable[[Settings], Connector]] = {
    "bcentral_api": BcentralApiConnector,
}

PARSERS: dict[str, Callable[[RawFile, Source], list[Observation]]] = {
    "bcentral_api": lambda raw, source: bcentral_api.parse(raw.content, source.series, raw.media_type),
}
