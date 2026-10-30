# Fixtures

Archivos reales de las fuentes, guardados para que los tests de los parsers no dependan de internet.

- **Procedencia:** cada archivo está en `MANIFEST.yaml`, con su origen, el período del dato y su sha256.
- **Limpieza:** antes de copiarlos se les quitan los nombres de personas y la ruta local de sus metadatos con
  `sanitize_xlsx.py`. Las hojas no cambian. Por eso `sha256` difiere de `sha256_original` (el del archivo del INE).
- **Nombres:** `<source_id>_<AAAA-MM del dato>.<ext>`. El período sale del contenido o del nombre original, no de la
  carpeta de descarga.
- **Agregar uno:** copiarlo con `sanitize_xlsx.py`, registrarlo en `MANIFEST.yaml` y correr `make test`. El test
  `test_fixtures.py` falla si un archivo no está en el manifiesto o si no coincide con él.
- **Nunca:** credenciales, datos de empresas, la marca de la empresa ni archivos de más de 500 KB.

Pendientes (fase 1): respuestas reales de Senado (HTML), de la API de noticias del INE y de la API BDE, capturadas
con User-Agent honesto. Empleo regional: falta definir qué archivo publica el INE en su noticia (en V1 casi solo había PDF).
