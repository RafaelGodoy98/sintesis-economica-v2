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
    assert (stored.created, stored.sha256, stored.size, stored.uri) == (
        True,
        sha,
        len(raw.content),
        expected.as_uri(),
    )


def test_same_content_twice_keeps_one_file_even_on_another_day(tmp_path):
    storage = LocalStorage(tmp_path)
    first = storage.save(make_raw(day=3))
    second = storage.save(make_raw(day=4))
    assert len(all_files(tmp_path)) == 1
    assert second.created is False
    assert second.uri == first.uri


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
    # este reproduce la falla de la primera corrida real (as_uri exige ruta absoluta).
    monkeypatch.chdir(tmp_path)
    stored = LocalStorage(Path("data") / "raw").save(make_raw())
    assert stored.uri.startswith("file:///")
    assert LocalStorage(Path("data") / "raw").save(make_raw()).created is False
