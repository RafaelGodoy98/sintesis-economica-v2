"""Canario de credenciales (idea de Rafael, 1.2): vigila las credenciales por su VALOR, en todos los tests.

En cada test, las credenciales BDE son falsas pero reconocibles, y el test corre en una carpeta vacía (nunca
lee el .env real). Al terminar, se buscan en todo lo que salió
(logs de cualquier librería a nivel DEBUG, pantalla y errores). Si aparecen, el test falla, aunque nadie haya
escrito un test de credenciales para esa pieza. Límite: solo vigila el código que los tests ejecutan.
"""

import logging
from urllib.parse import quote

import pytest

from sintesis_ingest.log import clear_secrets

pytest_plugins = ["pytester"]  # permite probar que la alarma del canario suena (test_canary.py)

CANARY_USER = "canario-7f3a@example.com"
# Falsa a propósito; el "#" sirve para probar también su forma codificada en URL (%23).
CANARY_PASSWORD = "CANARIO-7f3a-clave#"  # noqa: S105  # pragma: allowlist secret
CANARIES = {CANARY_USER, CANARY_PASSWORD, quote(CANARY_PASSWORD, safe=""), "CANARIO-7f3a", "canario-7f3a"}


@pytest.fixture(autouse=True)
def credential_canary(monkeypatch, caplog, capsys, tmp_path):
    # Cada test corre en una carpeta vacía: ninguno puede leer el .env real (con las credenciales de Rafael).
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SINTESIS_BDE_USER", CANARY_USER)
    monkeypatch.setenv("SINTESIS_BDE_PASSWORD", CANARY_PASSWORD)
    caplog.set_level(logging.DEBUG)  # graba TODO, incluso lo que en producción no se mostraría
    clear_secrets()
    yield
    clear_secrets()
    out = capsys.readouterr()
    places = {
        # get_records: en el cierre, `caplog.records` solo trae los del cierre (vacíos);
        # aquí van todas las etapas.
        "logs": "\n".join(
            f"{r.getMessage()} {vars(r)}"
            for when in ("setup", "call", "teardown")
            for r in caplog.get_records(when)
        ),
        "pantalla (stdout)": out.out,
        "errores (stderr)": out.err,
    }
    leaks = sorted(where for where, text in places.items() if any(c in text for c in CANARIES))
    if leaks:
        pytest.fail(f"CANARIO: la credencial de prueba se filtró en: {', '.join(leaks)}", pytrace=False)


@pytest.fixture
def canary():
    """Las credenciales canario, para los tests que verifican que viajan al servidor pero no se muestran."""
    return {"user": CANARY_USER, "password": CANARY_PASSWORD}
