# Guía del código (fase 1)

Qué hace cada pieza de `ingest/`, en lenguaje simple. Para cada una: su analogía, qué **garantiza** y qué test lo
demuestra. El *qué* y el *por qué* están aquí; el *cómo* está en el código.

## El recorrido completo

```
sintesis-ingest run --source bcentral_imacec          (el jefe de turno: cli.py)
   │
   ├─ lee la configuración ............................ config.py + sources.yaml + .env
   ├─ le da al censor las credenciales ................ log.py
   └─ por cada fuente:
        conector (bcentral_api.py) ── pide ──▶ mensajero (http.py) ──▶ API del Banco Central
             │
             └─ entrega formularios RawFile (contract.py): el JSON tal cual, con su huella sha256
                    ├─▶ archivo histórico (storage.py) .......... data/raw/   (solo lo nuevo)
                    ├─▶ traductor (parsers/bcentral_api.py) ..... filas (series_id, period, value)
                    │      └─▶ observations.py ................. data/observations/  (CSV)
                    └─▶ libro de turnos (audit.py) ............. data/ops/runs.jsonl
```

Todo esto viaja dentro de **la caja** (`ingest/Dockerfile`): la misma imagen corre en tu máquina y, desde la fase
4, en Cloud Run.

## Las piezas

| Pieza | Analogía | Qué garantiza | Lo demuestra |
|---|---|---|---|
| `config.py` + `sources.yaml` | **El manual de operación** | Qué fuentes y series existen (`sources.yaml`, igual en todo entorno) y qué cambia por máquina (`Settings`: carpeta de datos, email de contacto, credenciales). Un `sources.yaml` mal escrito o un dato obligatorio que falta (p. ej. el email de contacto) detienen todo antes de empezar; si falla, el error no muestra valores. **Ojo:** una variable `SINTESIS_*` mal escrita se ignora (no avisa) | `test_config.py` |
| `log.py` | **La bitácora con censor** | Cada evento es una línea JSON con `run_id` y `source_id`, que Cloud Logging sabe filtrar. El censor tapa con `***` lo que sigue a `user=`, `pass=`, `token=`, `key=` o `secret=`, y también los valores exactos de las credenciales, donde aparezcan | `test_log.py` |
| `http.py` | **El mensajero** | Es el único que habla con internet. Se presenta con nombre y contacto, espera 2 s entre pedidos, insiste ante caídas (5xx, 429, red) y no ante errores sin arreglo (404). Nunca deja ver la clave: ni en la URL que devuelve, ni en logs, ni en errores | `test_http.py` |
| `contract.py` | **El formulario** | Todo conector entrega lo mismo: `RawFile` con los bytes tal cual, la fuente, la URL sin credenciales y la hora (UTC). La huella se calcula del contenido. Todo parser entrega `Observation` (`series_id`, `period`, `value`) | `test_contract.py` |
| `storage.py` | **El archivo histórico** | Guarda cada contenido una sola vez, aunque llegue otro día (lo reconoce por su huella). Nunca sobrescribe. Si se corta a mitad, no deja archivos a medias | `test_storage.py` |
| `connectors/bcentral_api.py` | **El que sabe qué pedir** | Pide al Banco Central la historia completa de cada serie (por las revisiones). No acepta un "éxito" falso: HTTP 200 con `Codigo=-5` es un error | `test_bcentral_api.py` |
| `parsers/bcentral_api.py` | **El traductor** | Convierte el JSON en filas exactas (`Decimal`, sin redondeo), lee la codificación que declara el servidor (regla WHATWG), excluye y avisa las filas raras, y falla ante un formato desconocido en vez de adivinar. **No calcula nada:** las variaciones van en Dataform | `test_bcentral_api.py` |
| `registry.py` | **La guía de contactos** | Qué conector y qué traductor usa cada tipo de fuente. Sumar una fuente = una línea | (usado en `test_cli.py`) |
| `observations.py` | **El que pasa en limpio** | Un CSV por archivo raw, con el nombre de su huella: correr dos veces no duplica, y para reprocesar basta borrar los CSV | `test_cli.py` |
| `audit.py` | **El libro de turnos** | Una línea por fuente y corrida: cómo le fue, cuántos archivos nuevos, cuántas filas, cuánto tardó y el error (censurado). Solo se agrega, nunca se edita | `test_cli.py` |
| `cli.py` | **El jefe de turno** | Une todo con una orden. Una fuente que falla no detiene a las demás. Termina con un número que una máquina entiende: 0 bien · 1 falló una fuente · 2 no pudo empezar | `test_cli.py` |
| `ingest/Dockerfile` + `docker-compose.yml` (raíz) | **La caja** | La imagen trae Python, las librerías y el código; no trae el `.env`, ni tests, ni uv. Corre sin privilegios. Las credenciales entran al correr | `test_docker.py`, `test_docker_image.py` (`make test-docker`) |
| `tests/conftest.py` | **El canario** | En **todos** los tests: credenciales falsas reconocibles y una carpeta vacía (ningún test ve tu `.env`). Si la credencial aparece en logs o pantalla, el test falla | `test_canary.py` (prueba que la alarma suena) |
| `tests/fixtures/` | **Las muestras de laboratorio** | Respuestas reales guardadas byte a byte, con su huella en `MANIFEST.yaml`. Los tests nunca usan internet | `test_fixtures.py` |

## Dónde quedan los datos (local)

| Carpeta | Qué hay | Regla |
|---|---|---|
| `data/raw/source=<id>/ingest_date=<fecha>/<sha256>_<nombre>` | Lo que entregó la fuente, tal cual | Inmutable; una vez por contenido |
| `data/observations/source=<id>/<sha256>.csv` | `source_id, series_id, period, value, file_sha256, raw_path, ingest_date` | Se regenera desde raw |
| `data/ops/runs.jsonl` | El libro de turnos | Solo se agrega |

## Comandos

`make test` (rápido, sin internet) · `make test-docker` (la caja, aislada) · `make lint` · `make run-local SOURCE=<id>`
· `make docker-build` · `make docker-run SOURCE=<id>`

## Lo que viene

En la fase 2, los CSV se cargan a BigQuery (`raw`) y Dataform calcula las variaciones (`stg`, `marts`). En las fases 3
y 4, el archivo histórico pasa de `data/` a Cloud Storage y la caja corre sola en Cloud Run cada mes.
