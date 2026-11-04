"""Cliente HTTP común: el único que habla con internet.

Aplica una sola vez, para todas las fuentes, las reglas de CLAUDE.md:
- User-Agent honesto con contacto y pausa entre solicitudes.
- Reintentos solo cuando tiene sentido (red, 5xx, 429).
- Las credenciales nunca salen del cliente: ni en la URL que devuelve, ni en logs, ni en errores.
"""

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

from sintesis_ingest import __version__

logger = logging.getLogger(__name__)

# httpx registra cada solicitud en INFO con la URL COMPLETA (credenciales incluidas).
# La silenciamos en el origen; nuestros propios logs usan la URL pública.
# `redact` (log.py) queda como segunda barrera.
logging.getLogger("httpx").setLevel(logging.WARNING)

REPO_URL = "https://github.com/RafaelGodoy98/sintesis-economica-v2"


class FetchError(Exception):
    """La descarga falló. El mensaje nunca contiene credenciales."""


@dataclass(frozen=True)
class Response:
    url: str  # URL pública: sin parámetros secretos
    status: int
    content: bytes = field(repr=False)
    content_type: str  # encabezado completo, p. ej. "application/json; charset=utf-8"


def _query(params: Mapping[str, str]) -> str:
    # Se arma a mano y no con `params=` de httpx: este codificaría `@` como `%40`, y la API BDE
    # rechaza el usuario (email) así codificado (spike 1.1). `@` es válido en una query (RFC 3986).
    return "&".join(f"{quote(k, safe='')}={quote(str(v), safe='@')}" for k, v in params.items())


def _with_query(url: str, params: Mapping[str, str]) -> str:
    return f"{url}?{_query(params)}" if params else url


class HttpClient:
    def __init__(
        self,
        contact_email: str,
        pause_seconds: float = 2.0,
        *,
        max_attempts: int = 3,
        backoff_seconds: float = 2.0,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,  # los tests pasan un MockTransport
        sleep: Callable[[float], None] = time.sleep,  # los tests pasan uno falso: sin esperas reales
    ) -> None:
        self.pause_seconds = pause_seconds
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._has_requested = False
        self._client = httpx.Client(
            headers={"User-Agent": f"sintesis-economica-v2/{__version__} (+{REPO_URL}; {contact_email})"},
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def get(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
        secret_params: Mapping[str, str] | None = None,
    ) -> Response:
        """GET con pausa y reintentos. `secret_params` viajan en la URL pero nunca se muestran."""
        public_url = _with_query(url, dict(params or {}))
        full_url = _with_query(url, {**(params or {}), **(secret_params or {})})

        for attempt in range(1, self.max_attempts + 1):
            self._pause()
            try:
                resp = self._client.get(full_url)
            except httpx.TransportError as e:  # red, DNS, timeout
                reason = type(e).__name__  # solo el tipo: el mensaje puede traer la URL completa
            else:
                if resp.is_success:
                    logger.debug("descarga lista", extra={"url": public_url, "status": resp.status_code})
                    return Response(
                        public_url, resp.status_code, resp.content, resp.headers.get("content-type", "")
                    )
                reason = f"HTTP {resp.status_code}"
                if not (resp.status_code >= 500 or resp.status_code == 429):
                    # Un 404 o un 401 no se arreglan reintentando.
                    raise FetchError(f"GET {public_url} falló: {reason}") from None
            if attempt < self.max_attempts:
                wait = self.backoff_seconds * 2 ** (attempt - 1)
                logger.warning(
                    "reintento",
                    extra={"url": public_url, "attempt": attempt, "reason": reason, "wait_seconds": wait},
                )
                self._sleep(wait)
        # `from None`: sin esto, el traceback arrastraría la excepción de httpx,
        # que lleva la URL con credenciales.
        raise FetchError(f"GET {public_url} falló tras {self.max_attempts} intentos: {reason}") from None

    def _pause(self) -> None:
        """Pausa entre solicitudes (no antes de la primera): cortesía con la fuente."""
        if self._has_requested and self.pause_seconds:
            self._sleep(self.pause_seconds)
        self._has_requested = True

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
