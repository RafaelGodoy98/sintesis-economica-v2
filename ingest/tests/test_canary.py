"""La alarma del canario suena: se corre un mini proyecto de tests con el mismo conftest y fugas a propósito.

En un proceso aparte: así las fugas provocadas aquí no llegan al canario de este mismo test.
"""

from pathlib import Path

CONFTEST = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")


def run_inner(pytester, capsys, test_code: str):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_code)
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    # pytester repite en pantalla la salida interna (con la fuga provocada); ya está en `result`.
    capsys.readouterr()
    return result


def test_alarm_rings_when_a_log_contains_the_password(pytester, capsys):
    result = run_inner(
        pytester,
        capsys,
        """
import logging, os
def test_leaky():
    logging.getLogger("una.libreria").debug("conectando con clave %s", os.environ["SINTESIS_BDE_PASSWORD"])
""",
    )
    result.assert_outcomes(passed=1, errors=1)  # el test corre, pero el canario lo marca como error
    result.stdout.fnmatch_lines(["*CANARIO*logs*"])


def test_alarm_rings_when_the_user_is_printed(pytester, capsys):
    result = run_inner(
        pytester,
        capsys,
        """
import os
def test_leaky():
    print("usuario:", os.environ["SINTESIS_BDE_USER"])
""",
    )
    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["*CANARIO*stdout*"])


def test_alarm_rings_for_url_encoded_password(pytester, capsys):
    result = run_inner(
        pytester,
        capsys,
        """
import logging, os
from urllib.parse import quote
def test_leaky():
    logging.getLogger("x").info("GET ...&pass=%s", quote(os.environ["SINTESIS_BDE_PASSWORD"], safe=""))
""",
    )
    result.assert_outcomes(passed=1, errors=1)


def test_clean_test_passes(pytester, capsys):
    result = run_inner(
        pytester,
        capsys,
        """
import logging
def test_clean():
    logging.getLogger("x").info("descarga lista")
""",
    )
    result.assert_outcomes(passed=1)


def test_tests_never_see_the_real_env_file():
    # El canario corre cada test en una carpeta vacía: el .env real (con credenciales) no está a la vista.
    assert not Path(".env").exists()
