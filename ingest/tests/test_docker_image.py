"""La imagen, probada de forma aislada: sin el repo, sin credenciales y sin internet (make test-docker).

Comprueba lo que en la 1.5 se revisó a mano, para que quede revisado siempre (en la CI desde la fase 5).
La corrida contra la API real es la prueba de aceptación, y no va aquí: necesitaría credenciales y le
pediría datos al Banco Central en cada corrida de tests.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "sintesis-ingest:test"
DOCKER = shutil.which("docker")  # ruta completa del ejecutable (no se busca en el PATH en cada llamada)


@pytest.fixture(scope="module")
def image() -> str:
    if DOCKER is None:
        pytest.skip("docker no está disponible")
    # S603: los argumentos son fijos, escritos en este archivo; no hay entrada externa.
    build = subprocess.run(  # noqa: S603
        [DOCKER, "build", "-f", "ingest/Dockerfile", "-t", IMAGE, "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr[-2000:]
    return IMAGE


def docker_run(image: str, *args: str, sh_command: str | None = None) -> subprocess.CompletedProcess:
    # --network none: el contenedor no puede salir a internet. Ningún test de la imagen depende de la red.
    cmd = [DOCKER, "run", "--rm", "--network", "none"]
    cmd += ["--entrypoint", "sh", image, "-c", sh_command] if sh_command else [image, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # noqa: S603 (argumentos fijos)


def test_runs_as_a_non_root_user(image):
    assert docker_run(image, sh_command="id -u").stdout.strip() == "10001"


def test_contains_no_env_files_tests_or_uv(image):
    found = docker_run(
        image,
        sh_command="find / -xdev \\( -name '.env*' -o -path '*sintesis*test*' \\) 2>/dev/null; command -v uv",
    ).stdout.strip()
    assert found == ""


def test_works_on_its_own_without_the_repo(image):
    result = docker_run(image, "run", "--help")
    assert result.returncode == 0
    assert "--source" in result.stdout


def test_without_configuration_it_does_not_start(image):
    # Sin SINTESIS_CONTACT_EMAIL (ni credenciales): CRITICAL y código 2, sin intentar descargar nada.
    result = docker_run(image, "run", "--source", "bcentral_uf")
    assert result.returncode == 2
    assert '"severity": "CRITICAL"' in result.stdout
