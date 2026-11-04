# Fixtures

Archivos reales de las fuentes, guardados para que los tests de los parsers no dependan de internet.

- **Procedencia:** cada archivo está en `MANIFEST.yaml`, con su origen, el período del dato y su sha256.
- **Limpieza (xlsx del INE):** antes de copiarlos se les quitan los nombres de personas y la ruta local de sus metadatos con
  `sanitize_xlsx.py`. Las hojas no cambian. Por eso `sha256` difiere de `sha256_original` (el del archivo del INE).
- **API BDE:** respuestas JSON guardadas sin cambios (no traen metadatos personales ni credenciales); se revisó que
  no contengan el usuario ni la clave antes de copiarlas.
- **Nombres:** `<source_id>_<AAAA-MM del dato>.<ext>` (en la API BDE, `<source_id>_<serie_id>_<AAAA-MM>.json`). El período sale del contenido o del nombre original, no de la
  carpeta de descarga.
- **Agregar uno:** un xlsx se copia con `sanitize_xlsx.py`; un JSON de API se copia tal cual (bytes exactos), después
  de revisar que no traiga credenciales. Luego se registra en `MANIFEST.yaml` y se corre `make test`. El test
  `test_fixtures.py` falla si un archivo no está en el manifiesto o si no coincide con él.
- **Respuestas de error** (p. ej. `bcentral_uf_credenciales_invalidas.json`): llevan el caso en vez del período.
  El `source_url` registra la consulta real con la que se bajó el fixture, aunque difiera de `sources.yaml`.
- **Nunca:** credenciales, datos de empresas, la marca de la empresa ni archivos de más de 500 KB.

Pendientes: respuestas reales de Senado (HTML) y de la API de noticias del INE, capturadas
con User-Agent honesto. Empleo regional: falta definir qué archivo publica el INE en su noticia (en V1 casi solo había PDF).
