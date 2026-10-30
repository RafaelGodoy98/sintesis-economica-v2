# ADR-0003: Ingesta con conectores propios y contrato común

**Estado:** Aceptada · **Fecha:** 2026-10-30

## Contexto
Cada fuente se extrae de forma distinta:
- **API BDE del Banco Central:** autenticada, JSON.
- **INE regional:** API de noticias, scraping HTML y xlsx desordenados.
- **Senado:** GET con una cadena de parámetros y una tabla HTML con codificación mixta.

V1 tenía un "conector" por fuente que descargaba, parseaba y guardaba un Excel, todo junto. Hay que decidir cómo se
construye la extracción en V2.

Restricciones:
- **Fuentes de nicho:** ninguna herramienta trae resuelto el INE regional ni el Senado; la API BDE es la única "estándar".
- **Arquitectura ELT (ADR-0001):** el archivo original debe guardarse intacto en GCS antes de cualquier parseo.
- **Reglas de CLAUDE.md:** User-Agent honesto y pausa entre solicitudes; credenciales nunca en logs.
- **Portafolio:** el diseño debe poder explicarse y testearse con fixtures (0.8), sin internet.

## Opciones consideradas
### A. Conectores propios con un contrato común
Cada conector solo **descarga** y entrega: bytes del archivo, nombre, tipo, URL sin credenciales y fecha. El
almacenamiento (sha256 y GCS) y el parseo son piezas aparte, iguales para todas las fuentes.
- A favor: encaja con fuentes de nicho y con "raw primero"; cada pieza se testea por separado; el cliente HTTP común
  aplica una sola vez el User-Agent, la pausa y la redacción de credenciales; agregar una fuente = un conector más.
- En contra: hay que escribir y mantener cada conector; reintentos, paginación y esquema no vienen resueltos.

### B. dlt (*data load tool*, librería de Python)
- A favor: describe APIs REST de forma declarativa e infiere esquemas; le calza bien a la API BDE.
- En contra: el scraping HTML y los xlsx desordenados seguirían siendo código propio dentro de dlt; carga filas a
  BigQuery, no el archivo original, así que igual habría que guardar el raw aparte; es una abstracción más por aprender.

### C. Airbyte
- A favor: cientos de conectores listos y una interfaz gráfica.
- En contra: no tiene conectores para el INE regional ni para el Senado, y su constructor sin código apunta a APIs, no a
  HTML ni a xlsx; autoalojado exige una plataforma pesada siempre encendida; la versión en su nube es de pago.

### D. Singer / Meltano (*taps* y *targets*)
- A favor: especificación abierta para separar extracción y carga.
- En contra: igual habría que escribir *taps* propios para casi todas las fuentes, más el andamiaje del framework.

### E. Conectores propios con contrato común, más dlt solo para APIs REST (hoy, la API BDE)
- A favor: dlt se usa donde calza (REST con JSON: autenticación, reintentos, paginación y esquema declarados), y las
  fuentes desordenadas (Senado: HTML; INE: xlsx) siguen con conectores propios; se aprende dlt en un caso real.
- En contra:
  - Dos formas de hacer ingesta en el mismo repo, que hay que explicar.
  - Según su documentación (v1.32), **dlt no guarda la respuesta original**, solo datos normalizados (jsonl/parquet,
    con GCS como *staging*). Para cumplir "raw primero" en la API BDE habría que guardar el JSON con código propio, o
    aceptar como raw los archivos normalizados de dlt.
  - Su documentación no dice si sus modos de carga a BigQuery usan DML (no disponible en sandbox). Hay que probarlo.

## Decisión
_Opción A: conectores propios con contrato común como base para todas las fuentes. dlt se probará solo en una rama
experimental; si demuestra ser muy prometedor, se evaluará un cambio de arquitectura con un ADR nuevo. No quiero
debilitar los pasos del pipeline por usar una herramienta llamativa si este no es su caso de aplicación: aquí hay una
sola API REST simple, y el resto de las fuentes son HTML y xlsx. dlt rinde más con muchas APIs complejas (paginación,
JSON anidado, cargas incrementales)._

_(Redactada por Claude a partir de lo que dijo Rafael en la sesión del 2026-10-30; Rafael la revisa.)_

## Consecuencias
- **Contrato en la fase 1:** el conector solo descarga y entrega bytes, nombre, tipo, URL sin credenciales y fecha. El
  almacenamiento (sha256, GCS) y el parseo son piezas comunes, y un cliente HTTP común aplica el User-Agent, la pausa,
  los reintentos y la redacción de credenciales.
- **Se escribe y se mantiene más código** (reintentos, esquema). Se compensa con tests sobre fixtures (0.8).
- **Experimento con dlt:** después del conector propio de la API BDE, una rama `experiment/dlt-bde` hace lo mismo con
  dlt para comparar líneas de código, comportamiento en el sandbox (¿usa DML?) y qué queda guardado. El resultado se
  documenta, y no se integra a `main` salvo que haya un ADR nuevo.

## Referencias
- `docs/plan.md` §1 (conocimiento rescatable de V1), §4 (estructura `connectors/`, `parsers/`, `storage.py`).
- `docs/fuentes.md` (ficha Senado y notas del INE regional).
- dlt: https://dlthub.com/docs (REST API source, destino BigQuery, staging; consultados el 2026-10-30) · Airbyte: https://docs.airbyte.com · Meltano: https://docs.meltano.com
