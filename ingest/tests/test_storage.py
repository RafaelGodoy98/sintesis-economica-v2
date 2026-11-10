import hashlib
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from sintesis_ingest.contract import RawFile
from sintesis_ingest.storage import LocalStorage


def make_raw(content=b'{"a": 1}', day=3):
    return RawFile(
        source_id="fuente_prueba",
        name="datos.json",
        content=content,
        media_type="application/json",
        source_url="https://example.test/datos",
        fetched_at=datetime(2026, 11, day, 12, 0, tzinfo=UTC),
    )


def all_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def test_saves_original_bytes_in_raw_layout(tmp_path):
    raw = make_raw()
    stored = LocalStorage(tmp_path).save(raw)
    sha = hashlib.sha256(raw.content).hexdigest()
    expected = tmp_path / "source=fuente_prueba" / "ingest_date=2026-11-03" / f"{sha}_datos.json"
    assert all_files(tmp_path) == [expected]
    assert expected.read_bytes() == raw.content
    assert (stored.created, stored.sha256, stored.size, stored.raw_path, stored.ingest_date) == (
        True,
        sha,
        len(raw.content),
        f"source=fuente_prueba/ingest_date=2026-11-03/{sha}_datos.json",
        date(2026, 11, 3),
    )


def test_same_content_twice_keeps_one_file_even_on_another_day(tmp_path):
    storage = LocalStorage(tmp_path)
    first = storage.save(make_raw(day=3))
    second = storage.save(make_raw(day=4))
    assert len(all_files(tmp_path)) == 1
    assert second.created is False
    assert second.raw_path == first.raw_path


def test_different_content_creates_new_file(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.save(make_raw(content=b"version 1"))
    stored = storage.save(make_raw(content=b"version 2"))
    assert stored.created is True
    assert len(all_files(tmp_path)) == 2


def test_explicit_ingest_date_wins(tmp_path):
    LocalStorage(tmp_path).save(make_raw(), ingest_date=date(2026, 1, 15))
    (path,) = all_files(tmp_path)
    assert path.parent.name == "ingest_date=2026-01-15"


def test_failed_write_leaves_no_file(tmp_path, monkeypatch):
    def broken_replace(*args):
        raise OSError("corte a mitad de escritura")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        LocalStorage(tmp_path).save(make_raw())
    assert all_files(tmp_path) == []  # ni el archivo final ni el temporal


def test_works_with_the_relative_default_data_dir(tmp_path, monkeypatch):
    # En local, SINTESIS_LOCAL_DATA_DIR vale "data" (relativa). Los demás tests usan rutas absolutas;
    # este reproduce el caso de la primera corrida real (1.4), que falló con la ruta relativa.
    monkeypatch.chdir(tmp_path)
    stored = LocalStorage(Path("data") / "raw").save(make_raw())
    assert stored.raw_path.startswith("source=fuente_prueba/")
    assert LocalStorage(Path("data") / "raw").save(make_raw()).created is False


def test_raw_path_is_relative_and_hides_the_machine(tmp_path):
    # raw_path sube a BigQuery: no debe llevar la carpeta de la máquina (/home/<usuario>/...) ni un esquema
    # (file://). Así es la misma en local, en Docker y en la nube (decisión 3 de la 2.2).
    stored = LocalStorage(tmp_path).save(make_raw())
    assert not stored.raw_path.startswith(("/", "file:"))
    assert str(tmp_path) not in stored.raw_path
    assert stored.raw_path.split("/")[:2] == ["source=fuente_prueba", "ingest_date=2026-11-03"]


def test_ingest_date_is_the_first_save_even_when_seen_again(tmp_path):
    # La misma edición descargada otro día conserva la fecha en que llegó por primera vez (decisión 4,
    # 2.2): si no, reprocesar movería la historia de las ediciones (vintages).
    storage = LocalStorage(tmp_path)
    storage.save(make_raw(day=3))
    again = storage.save(make_raw(day=20))
    assert again.created is False
    assert again.ingest_date == date(2026, 11, 3)
