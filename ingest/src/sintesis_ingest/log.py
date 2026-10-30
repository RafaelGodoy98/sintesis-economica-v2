"""Logs en JSON, una línea por evento, a stdout (Cloud Run los envía a Cloud Logging)."""

import json
import logging
import re
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TextIO

_context: ContextVar[dict[str, str]] = ContextVar("log_context")

# Atributos que trae todo LogRecord; el resto son extras pasados con `extra={...}`.
_RECORD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}

# La API BDE pasa usuario y clave en la URL: nunca deben llegar a los logs.
_SECRET_PARAM = re.compile(r"(?i)\b(user|pass|password|token|key|api_?key|secret)=([^&\s\"']+)")


def redact(text: str) -> str:
    """Reemplaza el valor de parámetros sensibles (`user=`, `pass=`, `token=`, ...) por `***`."""
    return _SECRET_PARAM.sub(r"\1=***", text)


def new_run_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def log_context(**fields: str) -> Iterator[None]:
    """Agrega campos (p. ej. run_id, source_id) a todas las líneas de log dentro del bloque."""
    token = _context.set({**_context.get({}), **fields})
    try:
        yield
    finally:
        _context.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "severity": record.levelname,  # Cloud Logging lee `severity` y `message` como nivel y texto
            "message": record.getMessage(),
            "logger": record.name,
            **_context.get({}),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _RECORD_ATTRS})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, ensure_ascii=False, default=str))


def configure_logging(level: str = "INFO", stream: TextIO | None = None) -> None:
    """Configura el logger raíz. Idempotente: reemplaza el handler propio si ya existía.

    `stream` es stdout por defecto; los tests pasan un buffer en memoria.
    """
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, "_sintesis", False)]:
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._sintesis = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
