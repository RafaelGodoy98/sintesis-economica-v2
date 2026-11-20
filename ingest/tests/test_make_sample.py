"""`scripts/sample.sh` (make sample, 2.5): rechaza entradas mal formadas antes de llamar a BigQuery.

Un `bq` falso en el PATH deja una marca si alguien lo llama: así se comprueba que un TABLE que no tiene
la forma `dataset.tabla` (p. ej. con SQL agregado) nunca llega a ejecutarse.
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sample.sh"


def run_sample(tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "bq_called"
    fake_bq = bin_dir / "bq"
    fake_bq.write_text(f'#!/usr/bin/env bash\ntouch "{marker}"\n')
    fake_bq.chmod(0o755)
    full_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "DATA_DIR": str(tmp_path / "data"),
        **env,
    }
    result = subprocess.run(["bash", str(SCRIPT)], env=full_env, capture_output=True, text=True, timeout=30)  # noqa: S603, S607
    return result, marker


@pytest.mark.parametrize(
    "env",
    [
        {"TABLE": "marts.dim_series; DROP TABLE raw.observations"},
        {"TABLE": "dim_series"},
        {"TABLE": "marts.dim_series", "LIMIT": "10 OR 1=1"},
        {"TABLE": "marts.dim_series", "SQL": "consulta.sql"},
        {},
    ],
    ids=["sql_injected", "no_dataset", "bad_limit", "table_and_sql", "nothing"],
)
def test_sample_rejects_malformed_input_without_calling_bigquery(tmp_path: Path, env: dict[str, str]) -> None:
    result, marker = run_sample(tmp_path, **env)
    assert result.returncode == 2
    assert not marker.exists()


def test_sample_calls_bigquery_for_a_valid_table(tmp_path: Path) -> None:
    result, marker = run_sample(tmp_path, TABLE="marts.dim_series", LIMIT="5")
    assert result.returncode == 0, result.stderr
    assert marker.exists()
    assert (tmp_path / "data" / "samples" / "marts.dim_series.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_sample_writes_to_default_data_dir(tmp_path: Path) -> None:
    # Sin DATA_DIR, como en una corrida real: la salida va a ./data/samples relativo a donde se corre.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "bq").write_text("#!/usr/bin/env bash\necho 'a,b'\n")
    (bin_dir / "bq").chmod(0o755)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "TABLE": "marts.dim_series"}
    cmd = ["bash", str(SCRIPT)]
    result = subprocess.run(cmd, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30)  # noqa: S603
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data" / "samples" / "marts.dim_series.csv").exists()
