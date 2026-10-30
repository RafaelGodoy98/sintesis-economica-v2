"""Copia un xlsx quitando nombres de personas de sus metadatos; el contenido de las hojas no se toca.

Uso: python sanitize_xlsx.py ORIGEN DESTINO

Un xlsx es un zip. Solo se reescriben docProps/core.xml (autor, modificado por), docProps/app.xml
(empresa, administrador) y, en xl/workbook.xml, la ruta local donde se guardó el archivo (absPath);
el resto de las entradas, incluidas las hojas, se copia byte a byte.
"""

import re
import sys
import zipfile
from pathlib import Path

_BLANK_TAGS = {
    "docProps/core.xml": ("dc:creator", "cp:lastModifiedBy"),
    "docProps/app.xml": ("Company", "Manager"),
}


_ABS_PATH = re.compile(r'(<x15ac:absPath url=")[^"]*(")')


def _blank(xml: str, tags: tuple[str, ...]) -> str:
    for tag in tags:
        xml = re.sub(rf"<{tag}>[^<]*</{tag}>", f"<{tag}></{tag}>", xml)
    return xml


def sanitize(src: Path, dst: Path) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename in _BLANK_TAGS:
                data = _blank(data.decode("utf-8"), _BLANK_TAGS[info.filename]).encode("utf-8")
            elif info.filename == "xl/workbook.xml":
                data = _ABS_PATH.sub(r"\1\2", data.decode("utf-8")).encode("utf-8")
            zout.writestr(info, data)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sanitize(Path(sys.argv[1]), Path(sys.argv[2]))
