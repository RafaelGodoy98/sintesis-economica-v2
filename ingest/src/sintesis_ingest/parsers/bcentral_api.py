"""Parser de la API BDE: respuesta JSON de GetSeries → filas (serie_id, periodo, valor).

Solo limpieza estructural: texto → fecha y número. Nada de variaciones ni KPI (van en Dataform).
Formato verificado en el spike de la 1.1 y en la historia completa del IMACEC (docs/fuentes.md).
"""

import codecs
import json
import logging
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sintesis_ingest.contract import Observation, SourceError

logger = logging.getLogger(__name__)

# Codificación: se respeta la que declara el servidor (`Content-Type: ...; charset=`), traducida con la
# regla del estándar WHATWG Encoding (la de los navegadores): `iso-8859-1`, `latin1` y `ascii` se leen
# como windows-1252, que coincide con ellas en todo carácter imprimible e interpreta bien 0x80–0x9F.
# Sin declaración se usa cp1252: es lo verificado en la API BDE (1.1 y 1.3).
DEFAULT_ENCODING = "cp1252"
_WHATWG_AS_CP1252 = {
    "iso-8859-1",
    "iso8859-1",
    "latin1",
    "latin-1",
    "us-ascii",
    "ascii",
    "windows-1252",
    "cp1252",
}
DATE_FORMAT = "%d-%m-%Y"  # "01-09-2026"; las series mensuales fechan el día 1


def encoding_for(content_type: str | None) -> str:
    """Codificación a usar según el `Content-Type` declarado (regla WHATWG); cp1252 si no declara."""
    declared = None
    for param in (content_type or "").split(";")[1:]:  # "application/json; charset=ISO-8859-1"
        name, _, value = param.partition("=")
        if name.strip().lower() == "charset":
            declared = value.strip().strip('"').lower()
    if not declared or declared in _WHATWG_AS_CP1252:
        return DEFAULT_ENCODING
    try:
        return codecs.lookup(declared).name
    except LookupError:
        logger.warning("codificación declarada desconocida; se usa cp1252", extra={"charset": declared})
        return DEFAULT_ENCODING


def decode_response(content: bytes, content_type: str | None = None) -> dict:
    """Decodifica la respuesta y verifica `Codigo`: la API responde HTTP 200 incluso cuando falla."""
    try:
        data = json.loads(content.decode(encoding_for(content_type)))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SourceError(f"la respuesta de la API BDE no es JSON legible ({type(e).__name__})") from None
    if data.get("Codigo") != 0:
        raise SourceError(f"la API BDE respondió Codigo={data.get('Codigo')}: {data.get('Descripcion')}")
    return data


def parse(content: bytes, series: Mapping[str, str], content_type: str | None = None) -> list[Observation]:
    """`series`: serie_id → código BDE (sources.yaml); `content_type`: el declarado por el servidor.

    Devuelve las observaciones con statusCode OK.
    """
    data = decode_response(content, content_type)
    code = (data.get("Series") or {}).get("seriesId")
    by_code = {c: serie_id for serie_id, c in series.items()}
    if code not in by_code:
        raise SourceError(f"el código {code!r} no está en la configuración de la fuente")
    serie_id = by_code[code]

    rows: list[Observation] = []
    excluded: list[str] = []
    for obs in data["Series"].get("Obs") or []:
        if obs.get("statusCode") != "OK":
            excluded.append(f"{obs.get('indexDateString')}={obs.get('statusCode')}")
            continue
        try:
            periodo = datetime.strptime(obs["indexDateString"], DATE_FORMAT).date()
            valor = Decimal(obs["value"])
        except (KeyError, ValueError, InvalidOperation):
            # Un formato distinto al verificado es un cambio de la fuente:
            # mejor fallar que guardar datos malos.
            raise SourceError(f"{serie_id}: observación con formato inesperado: {obs!r}") from None
        if not valor.is_finite():
            raise SourceError(f"{serie_id}: valor no numérico con statusCode OK: {obs!r}")
        rows.append(Observation(serie_id, periodo, valor))

    if excluded:  # decisión 1.3: excluir y avisar; el raw queda intacto para reprocesar
        logger.warning(
            "observaciones excluidas por statusCode",
            extra={"serie_id": serie_id, "count": len(excluded), "examples": excluded[:10]},
        )
    if not rows:
        logger.warning("serie sin observaciones", extra={"serie_id": serie_id})
    return rows
