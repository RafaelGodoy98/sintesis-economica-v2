import hashlib
import re
import zipfile
from pathlib import Path

import pytest
import yaml

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = yaml.safe_load((FIXTURES / "MANIFEST.yaml").read_text(encoding="utf-8"))["fixtures"]
DATA_SUFFIXES = {".xlsx", ".xls", ".pdf", ".html", ".json", ".csv"}


def test_every_data_file_is_in_the_manifest():
    on_disk = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*") if p.suffix in DATA_SUFFIXES}
    assert on_disk == {f["file"] for f in MANIFEST}


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda f: f["file"])
def test_fixture_matches_manifest_sha256(entry):
    data = (FIXTURES / entry["file"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]


@pytest.mark.parametrize(
    "entry", [f for f in MANIFEST if f["file"].endswith(".xlsx")], ids=lambda f: f["file"]
)
def test_xlsx_has_no_personal_metadata(entry):
    with zipfile.ZipFile(FIXTURES / entry["file"]) as z:
        core = z.read("docProps/core.xml").decode("utf-8")
        workbook = z.read("xl/workbook.xml").decode("utf-8")
        sheets = re.findall(r'<sheet [^>]*name="([^"]*)"', workbook)
    assert re.search(r"<dc:creator>[^<]+<", core) is None
    assert re.search(r"<cp:lastModifiedBy>[^<]+<", core) is None
    assert re.search(r'absPath url="[^"]+"', workbook) is None
    assert sheets == [str(s) for s in entry["sheets"]]
