import hashlib
from datetime import UTC, datetime

import pytest

from sintesis_ingest.contract import RawFile


def make_raw(**kw):
    base = dict(
        source_id="fuente_prueba",
        name="datos.json",
        content=b'{"a": 1}',
        media_type="application/json",
        source_url="https://example.test/datos",
        fetched_at=datetime(2026, 11, 3, 12, 0, tzinfo=UTC),
    )
    return RawFile(**{**base, **kw})


def test_sha256_is_derived_from_content():
    assert make_raw().sha256 == hashlib.sha256(b'{"a": 1}').hexdigest()


def test_repr_does_not_dump_content():
    assert "content" not in repr(make_raw(content=b"x" * 1000))


@pytest.mark.parametrize("name", ["", "../escape.json", "carpeta/datos.json", "..", "a\\b.json"])
def test_file_name_cannot_contain_folders(name):
    with pytest.raises(ValueError, match="nombre de archivo"):
        make_raw(name=name)


def test_fetched_at_must_have_timezone():
    with pytest.raises(ValueError, match="zona horaria"):
        make_raw(fetched_at=datetime(2026, 11, 3, 12, 0))
