# Fichas de fuentes

Una ficha describe cómo V1 obtiene, parsea y valida una fuente, para portarla a V2 sin copiar código.
La redacta el subagente `v1-analista` (solo lectura sobre V1), Claude la contrasta con el código y Rafael la valida.
Recién con la ficha validada se planifica el conector de V2. Rutas citadas: relativas a V1.

| Fuente | `source_id` | Estado |
|---|---|---|
| Banco Central — API BDE (UF, IMACEC) | `bcentral_uf`, `bcentral_imacec` | Borrador verificado contra la API, pendiente de validación |
| Senado — proyectos de ley | `senado_proyectos_tramitacion`, `senado_leyes_publicadas` | Borrador, pendiente de validación |
| INE regional | `empleo_regional`, `energia_regional`, `exportaciones_regional`, `ipman_regional`, `isup_regional` | Sin ficha; notas previas abajo (0.8) |

---

## Banco Central de Chile — API BDE (`bcentral_uf`, `bcentral_imacec`)

**Estado:** borrador verificado contra la API (2026-11-03), pendiente de validación de Rafael.
**Contraste (Claude, 2026-11-03):** `scripts/conectores/bcentral_api.py`, `scripts/conectores/bcentral_estatico.py`,
`scripts/core/http.py` y `sintesis/config.yaml` revisados contra el borrador de `v1-analista`: sin discrepancias.
**Decisión de alcance (Rafael, 2026-11-03):** la rebanada vertical trae **UF + IMACEC (10 series), todo por la API BDE**.
El Excel estático del IMACEC que usaba V1 se descarta: un solo formato (JSON), sin layout de Excel frágil.

Requiere credenciales: `SINTESIS_BDE_USER` (el **email** registrado) y `SINTESIS_BDE_PASSWORD`. El acceso a la API se
activa aparte de la cuenta del sitio de la BDE.

### Resumen
- **V1, UF:** `GetSeries` de la API BDE, del día 1 del mes actual al último del mes siguiente; guarda un CSV
  (`scripts/conectores/bcentral_api.py:36-92`). Su código de serie **nunca se verificó** ("Pendiente de credenciales",
  `bcentral_api.py:3-8`): no consta que V1 haya funcionado contra la API real.
- **V1, IMACEC:** descargaba un Excel con URL fija en si3.bcentral.cl (`bcentral_estatico.py:9`) porque www.bcentral.cl
  está tras un WAF (`bcentral_estatico.py:5-8`). La síntesis consume 10 series del IMACEC (`sintesis/config.yaml:104-121`).
- **La UF no la consume nadie en V1** (`sintesis/textos.py:34-35`: "se usará en los cuadros"). El IMACEC es la serie
  con consumidor real y con cifras que contrastar contra V1 en la fase 2.

### Endpoint y método
- `GET https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx?user=…&pass=…&function=<F>&…` (`bcentral_api.py:21,52-56`).
  - `function=GetSeries`: `timeseries=<código>`, `firstdate`/`lastdate` en `AAAA-MM-DD`. Un código por consulta.
  - `function=SearchSeries`: `frequency=DAILY|MONTHLY|…`; devuelve el catálogo (`SeriesInfos`).
- **Usuario y clave van en la URL:** nunca loguear la URL completa ni el texto de excepciones que la contengan. V1 la
  imprimía al reintentar y en el reporte de errores (`scripts/core/http.py:23,26`; `scripts/main.py:42-43`).

### Verificado contra la API (2026-11-03)
Spike desechable (fuera del repo), corrido por Rafael con sus credenciales; Claude nunca vio la URL ni la clave.

- **El `@` del usuario debe ir sin codificar.** Con `%40` (lo que hace un cliente HTTP "estándar") la API rechaza las
  credenciales. Con `@` literal, como lo envía el navegador, funciona.
- **HTTP 200 incluso con error.** Credenciales inválidas → 200 con `Codigo=-5` ("Invalid username or password"). El
  éxito es `Codigo=0`, `Descripcion="Success"`. **El conector debe validar `Codigo`, no solo el status.**
- **Codificación cp1252, no UTF-8.** El catálogo y el `GetSeries` del IMACEC traen `í` como byte `0xED` (cp1252) y
  fallan al leerse como UTF-8. La respuesta de la UF es ASCII puro (válida en ambas), así que no prueba lo contrario.
  El raw se guarda tal cual (bytes) y el parser decodifica en cp1252 de forma explícita.
  **Actualización 1.3:** el servidor sí declara `Content-Type: application/json; charset=ISO-8859-1`. El `RawFile`
  guarda ese encabezado completo y el parser **respeta lo declarado** con la regla del estándar WHATWG Encoding (la de
  los navegadores): `iso-8859-1` se lee como windows-1252 (cp1252), que coincide en todo carácter imprimible e
  interpreta bien 0x80–0x9F (€, comillas). Si la fuente cambia a UTF-8 y lo declara, el parser lo sigue solo. En los
  fixtures no hay bytes 0x80–0x9F, el único rango donde ambas difieren.
- **Estructura de `GetSeries`:** `{Codigo, Descripcion, Series: {descripEsp, descripIng, seriesId, Obs: [...]},
  SeriesInfos: []}`. Cada observación: `{indexDateString: "dd-mm-aaaa", value: "<texto>", statusCode: "OK"}`.
  - El valor viene como **texto** con punto decimal (`"41215.77"`, `"111.2147495657"`).
  - Las series mensuales fechan el **día 1** del mes (`01-09-2026` = septiembre 2026).
- **UF publicada por adelantado:** pedida del 25-10 al 30-11-2026, la API devolvió hasta el **09-11-2026**. Los días aún
  no publicados **no aparecen** (no vienen como vacíos ni `NaN`).
- **IMACEC:** índices base 2018 desde 01-1996 (impuestos desde 01-2013) hasta 09-2026, actualizados el 02-11-2026.

**Códigos de serie** (títulos tomados del catálogo; la UF, de `descripEsp` de `GetSeries`, porque es diaria):

| `serie_id` (propuesto) | Código BDE | Título oficial | Qué usaba V1 (`config.yaml:104-121`) |
|---|---|---|---|
| `uf` | `F073.UFF.PRE.Z.D` | Unidad de fomento (UF) | (sin uso) |
| `imacec_total` | `F032.IMC.IND.Z.Z.EP18.Z.Z.0.M` | Imacec empalmado, serie original (índice 2018=100) | `imacec.var12` |
| `imacec_no_minero` | `F032.IMC.IND.Z.Z.EP18.N03.Z.0.M` | Imacec no minero, serie empalmada | `imacec.no_minero_var12` |
| `imacec_mineria` | `F032.IMC.IND.Z.Z.EP18.03.Z.0.M` | Imacec minero, serie empalmada | `imacec.mineria_var12` |
| `imacec_industria` | `F032.IMC.IND.Z.Z.EP18.04.Z.0.M` | Imacec industria, serie original | `imacec.industria_var12` |
| `imacec_resto_bienes` | `F032.IMC.IND.Z.Z.EP18.RB.Z.0.M` | Imacec resto de bienes, serie original | `imacec.resto_bienes_var12` |
| `imacec_comercio` | `F032.IMC.IND.Z.Z.EP18.COM.Z.0.M` | Imacec comercio, serie original | `imacec.comercio_var12` |
| `imacec_servicios` | `F032.IMC.IND.Z.Z.EP18.SERV.Z.0.M` | Imacec servicios, serie original | `imacec.servicios_var12` |
| `imacec_produccion_bienes` | `F032.IMC.IND.Z.Z.EP18.PB.Z.0.M` | Imacec producción de bienes, serie original | `imacec.bienes_var12` |
| `imacec_impuestos` | `F032.IMC.IND.Z.Z.EP18.IMP.Z.0.M` | Imacec impuestos sobre los productos, serie original | `imacec.impuestos_var12` |
| `imacec_total_desest` | `F032.IMC.IND.Z.Z.EP18.Z.Z.1.M` | Imacec empalmado, desestacionalizado (índice 2018=100) | `imacec.desest_var_mensual` |

- **Se traen índices, no variaciones.** V1 consumía variaciones (12 meses y mensual desestacionalizada). En V2 se
  calculan en Dataform desde los índices (regla del proyecto).
- **Trampa: las series `F032.IMC.V12.…` no son variaciones 12 meses.** El catálogo las titula "contribución año/año":
  cuántos puntos aporta un sector al crecimiento del total, no cuánto creció el sector. No usarlas como variación.

### Parseo y entidad (para la 1.3)
- Raw: la respuesta JSON tal cual, una por código o una por fuente (se decide en la 1.3).
- Entidad: `(serie_id, periodo, valor)`. `periodo` desde `indexDateString` (`dd-mm-aaaa`); `valor` de texto a decimal.
  Solo limpieza estructural; nada de cálculos.
- V1 no revisaba `Codigo` ni `statusCode`, ni convertía tipos (`bcentral_api.py:64-68`).

### Frecuencia y desfase esperado
- **UF:** diaria, publicada hasta el día 9 del mes siguiente.
- **IMACEC:** mensual. V1 espera un desfase de 2 meses entre el mes de edición y el último dato (`config.yaml:21-31`;
  `sintesis/verificar.py:17,41-56`). Septiembre 2026 se publicó el 02-11-2026, coherente con ese desfase.

### Validaciones de V1
- UF: solo que `Obs` no venga vacío y que existan credenciales (`bcentral_api.py:28-32,64-66`).
- IMACEC (Excel): status 200 y cuerpo no vacío (`http.py:18`). "Al día": `verificar.py` compara la última fecha de
  `imacec.var12` con la esperada (`verificar.py:45-55`).
- Errores por fuente: se registran y las demás fuentes siguen (`main.py:37-43`).

### Fallos conocidos y bloqueos
- **WAF en www.bcentral.cl** (`bcentral_estatico.py:5-8`, `scripts/core/alertas.py:6-9`): V2 no lo toca; la API está
  en si3.bcentral.cl. La nota de prensa PDF del IMACEC quedaba manual en V1 por ese bloqueo.
- V1 no distinguía credenciales malas, serie inexistente y falta de datos: todo terminaba en "no devolvió observaciones".

### Qué NO portar (y por qué)
- **URL con credenciales en logs** (`http.py:23,26`): prohibido en V2.
- **User-Agent que imita Chrome** (`http.py:4-9`): V2 usa uno honesto con contacto.
- **Excel del IMACEC y su parseo** (`bcentral_estatico.py`, `alertas.py:26-47`): reemplazado por la API.
- **CSV temporal de la UF, nombres por rango de meses, `guardar_archivo`, carpetas `_old` y Drive**
  (`bcentral_api.py:69-91`, `scripts/core/almacenamiento.py:73-142`): V2 usa raw inmutable con sha256.
- **Escala ×100 y variaciones** (`config.yaml:104-121`): van en Dataform; la escala es de presentación.

### Preguntas resueltas
- Código de la UF: `F073.UFF.PRE.Z.D`, confirmado. ¿IMACEC por la API?: sí, completo (tabla de arriba).
- ¿Hay variaciones ya calculadas?: no utilizables (`V12` son contribuciones). Se calculan en Dataform.
- ¿Se ingesta la UF sin consumidor?: sí, por decisión de alcance (rebanada vertical).
- Respuesta para fechas sin dato: se omiten (UF). Credenciales malas: `Codigo=-5` con HTTP 200.

### Decisiones de la 1.3 (Rafael, 2026-11-03)
1. **Ventana:** historia completa en cada corrida (UF desde 2000-01-01; IMACEC desde 1996-01-01), hasta hoy + 45 días.
   Captura las revisiones del IMACEC sin guardar estado; si nada cambió, el archivo es idéntico y no se guarda de nuevo.
2. **Raw:** un archivo por serie (`<serie_id>.json`), la respuesta tal cual.
3. **`statusCode` ≠ `OK`:** la fila se excluye y se registra un WARNING con cuántas y cuáles. En la historia completa
   del IMACEC total (369 meses) todas son `OK`. Un formato de fecha o valor distinto al verificado **falla**.
4. **Nota de prensa PDF:** pendiente para la fase 2, junto con el control de la variación publicada.

### Idea de control (Rafael, 2026-11-03): contrastar la variación calculada con la publicada
La variación del IMACEC desestacionalizado que publica el Banco Central **ya ha venido mal calculada**. Propuesta:
calcular la variación en Dataform desde el índice y compararla con la publicada; si difieren más que el redondeo,
emitir una alerta. **Dónde está la publicada:** la API no la trae (en el catálogo solo hay índices y
*contribuciones* `V12`/`VAR`). Candidatos: la hoja `desestacionalizado_variación` del Excel de si3 que usaba V1
(`bcentral_estatico.py:9`, `config.yaml:118-121`) o la nota de prensa (manual, por el WAF). Se decide en la fase 2
(junto con `validador-cifras`).

### Referencias (archivo:línea en V1)
- `scripts/conectores/bcentral_api.py:1-9,21-33,36-58,61-92` · `scripts/conectores/bcentral_estatico.py:5-26`
- `scripts/core/http.py:4-26` · `scripts/core/registro.py:192-208,221-230` · `scripts/core/almacenamiento.py:73-142`
- `scripts/core/alertas.py:6-9,26-47,66-82` · `scripts/main.py:37-48`
- `sintesis/config.yaml:21-31,104-121` · `sintesis/verificar.py:17,41-56` · `sintesis/textos.py:34-35`

---

## Senado de Chile — proyectos de ley (`senado_proyectos_tramitacion`, `senado_leyes_publicadas`)

En V2 son **dos fuentes** en `sources.yaml` (una por estado: `T` en tramitación, `L` publicada), cada una con su propio raw. En V1 el registro tenía un solo id (`senado`) que el conector no usaba.

**Estado:** borrador — pendiente de validación de Rafael.
**Contraste (Claude, 2026-10-30):** `scripts/conectores/senado.py`, `scripts/core/http.py`, `scripts/core/registro.py` y `sintesis/config.yaml` revisados contra la ficha: sin discrepancias, salvo la pregunta del `~` (resuelta abajo).

No requiere credenciales.

### Resumen
V1 reproduce la «Consulta avanzada» de tramitacion.senado.cl con un GET simple, sin JavaScript ni sesión (`scripts/conectores/senado.py:3-5`). Hace **dos consultas por corrida**:
- **proyectos**: proyectos de ley en tramitación (estado `T`), filtrados por fecha de **ingreso**.
- **leyes**: proyectos publicados como ley (estado `L`), filtrados por fecha de **publicación**.

Cada consulta devuelve una tabla HTML (Fecha · N° Boletín · Título · Estado). V1 la raspa con BeautifulSoup y la guarda en un Excel (`senado.py:91-124`).

### Endpoint(s) y método
- `GET https://tramitacion.senado.cl/appsenado/index.php?mo=tramitacion&ac=avanzada_resultado&cadena=<CADENA>` (`senado.py:35`).
- `<CADENA>`: 14 campos separados por `~`, codificada con `quote(..., safe="")` (`senado.py:59`). Las `/` de las fechas quedan como `%2F`. El `~` queda **literal**: desde Python 3.7, `quote` nunca codifica `~`. Lo verificó Claude; es coherente con `scripts/core/fuentes_urls.json:53,57`.
- Sin autenticación ni cookies. `requests.get` con timeout de 60 s (`senado.py:64`), 3 intentos y 2 s entre intentos (`scripts/core/http.py:12-26`). Éxito = status 200 y cuerpo no vacío (`http.py:18`).
- Sin pausa entre las dos consultas.
- Ejemplos (`fuentes_urls.json:51-58`):
  - proyectos: `cadena=0~0~1~T~01%2F09%2F2026~02%2F10%2F2026~~~0~0~~~~`
  - leyes: `cadena=0~0~1~L~~~01%2F09%2F2026~02%2F10%2F2026~0~0~~~~`

### Parámetros
Campos de `cadena`, en orden (`senado.py:8-15`; V1 los verificó en la pestaña Red del navegador el 02-10-2026). Armado en `senado.py:49-54`.

| # | Campo | Valores | Valor en V1 |
|---|---|---|---|
| 0 | iniciativa | 0 todas · 30 mensaje · 31 moción | `0` |
| 1 | cámara de origen | 0 ambas · S · D | `0` |
| 2 | tipo de proyecto | 1 proyecto de ley | `1` |
| 3 | estado | T en tramitación · L publicado | `T` / `L` |
| 4-5 | ingreso desde/hasta (dd/mm/aaaa) | | solo si se filtra por ingreso |
| 6-7 | publicación desde/hasta | | solo si se filtra por publicación |
| 8 | tipo de norma | 0 todas · LE · DS | `0` |
| 9 | urgencia | 0 no seleccionada | `0` |
| 10-13 | n° boletín, texto, mociones | | vacíos |

- Período por defecto: del día 1 del mes anterior hasta hoy (`senado.py:42-46`). `desde`/`hasta` solo se cambian en la prueba manual (`senado.py:127-139`); `scripts/main.py:38` no los pasa.
- **Tope del sitio:** 1.000 filas por consulta (`senado.py:36`). Si se alcanza, V1 solo avisa (`senado.py:71-72`); no pagina ni parte el período.

### Formato de respuesta
- HTML con tabla Fecha · N° Boletín · Título · Estado, más dos columnas ocultas (`senado.py:17`).
- **Codificación mixta:** los datos vienen en UTF-8 y partes de la plantilla en Latin-1. V1 decodifica como UTF-8 y lee como Latin-1 solo los bytes inválidos (`senado.py:38, 60-65`).
- Fechas en `dd/mm/aaaa` (inferido de `sintesis/proyectos_ley/armar.py:50`).
- La columna Estado de una ley contiene «… Ley N° 21.xxx …» (patrón en `armar.py:76`).

### Parseo (qué se extrae y cómo)
`consultar` (`senado.py:57-73`):
1. Recorre todos los `<tr>` y toma el texto de sus `<td>`.
2. Una fila es válida si tiene ≥ 4 celdas y la celda 1 tiene la forma `NNNN-NN` (contiene `-` y sin guiones son solo dígitos) (`senado.py:69`).
3. Conserva las 4 primeras celdas como texto. No convierte tipos.

### Salida / entidad resultante
V1 escribe dos xlsx por corrida (`senado.py:100-123`): `MM-AAAA Proyectos de Ley.xlsx` (`senado_proyectos`) y `MM-AAAA Leyes Aprobadas.xlsx` (`senado_leyes`). `MM-AAAA` sale de `hasta`.
- Hoja `dhtmlxGrid`: encabezado + una fila por proyecto.
- Hoja `consulta`: `consulta`, `filtro`, `desde`, `hasta`, `fecha_corte`, `filas`, `url` (`senado.py:76-88, 106-114`).

Entidad para V2 (inferido): una fila = `{fecha, boletin, titulo, estado}` + tipo de consulta (`proyecto` | `ley`) + fecha de corte. La clave natural es el N° de boletín.

Campos que consume `sintesis/proyectos_ley/armar.py`. El armado del boletín queda fuera de alcance; se anota solo como referencia de uso:
- `fecha`, `boletin`, `titulo` y `estado` (`armar.py:45-66`), y `desde`, `hasta` y `fecha_corte` de la hoja `consulta` (`armar.py:93-102`).
- Derivados:
  - Código de comisión = sufijo del boletín, rellenado a 2 dígitos (`armar.py:106`). Se cruza con `proyectos_ley.comisiones_interes` (`sintesis/config.yaml:204-215`), cuya lista está marcada «pendiente verificar» en V1.
  - N° de ley: regex `Ley N[°º]?\s*([\d.]+)` sobre `estado` (`armar.py:75-77`).
  - URL de ficha: `https://tramitacion.senado.cl/appsenado/templates/tramitacion/index.php?boletin_ini={boletin}` (`armar.py:33`).

### Frecuencia y desfase esperado
- Mensual, los primeros días del mes (`senado.py:43`). Registro: `scripts/core/registro.py:209-218`; despacho: `scripts/main.py:10,19,38`.
- Última corrida registrada: 2026-10-02, período 01/09/2026–02/10/2026 (`fuentes_urls.json:51-58`, `estado_descargas.json:54-59`).
- Sin desfase esperado: se consulta por rango de fechas, no como una serie con rezago. Falta confirmar en `verificar.py`/`cifras.py` (no revisados).

### Validaciones de V1
- Forma del N° de boletín (`senado.py:69`) y aviso si hay ≥ 1.000 filas (`senado.py:71-72`).
- HTTP 200 con cuerpo no vacío y 3 intentos (`http.py:18-26`).
- **No valida**:
  - cero filas: un resultado vacío se guarda como éxito;
  - nombres de columnas;
  - fechas válidas.

  Una página de error con status 200 daría cero filas sin fallar (inferido).

### Fallos conocidos y bloqueos
- Tope de 1.000 filas: riesgo de truncamiento silencioso.
- Codificación mixta UTF-8/Latin-1.
- Sin WAF documentado. V1 usa un User-Agent de Chrome falso (`http.py:5-8`).
- Las excepciones quedan registradas como error de la fuente y las demás fuentes siguen (`main.py:37-43`).
- El nombre del archivo depende solo de `hasta`: reejecutar en el mismo mes sobreescribe el resultado.

### Qué NO portar (y por qué)
- **User-Agent de Chrome falso:** CLAUDE.md exige un User-Agent honesto con contacto.
- **Excel y hoja `consulta` como canal de metadatos:** en V2 el raw es la respuesta y los metadatos van en el manifiesto, con sha256. `dhtmlxGrid` solo imitaba la exportación manual.
- **`guardar_archivo`, `estado_descargas.json`, `fuentes_urls.json`, archivado en `_Old` y `va_a_central`** (`scripts/core/almacenamiento.py:73-132`): V2 los reemplaza por raw inmutable en GCS.
- **Armado de PDF/HTML/correo y etiquetas de presentación:** fuera de alcance de V2.

### Preguntas abiertas para Rafael
1. ¿Raw = HTML crudo (fiel, idempotente por sha256, se reparsea sin volver a descargar) o la tabla extraída? V1 solo guarda la tabla.
2. Período: ¿mes anterior + días del mes en curso (V1, con solape y resultado que depende del día de ejecución) o ventanas mensuales cerradas?
3. Si se alcanzan las 1.000 filas: ¿fallar o partir el período?
4. Cero filas: ¿fallo o éxito válido?
5. ¿Sigue vigente la codificación mixta? Hace falta un HTML real como fixture (0.8).
6. ~~`~` literal o `%7E`~~ → resuelto: literal (ver Endpoint).
7. ¿Interesan las 2 columnas ocultas o los filtros no usados (iniciativa, cámara, urgencia)?
8. Comisiones de interés: ¿seed de dbt en V2 o fuera de alcance?
9. Confirmar si `verificar.py`/`cifras.py` mencionan esta fuente.
10. Términos de uso del sitio del Senado para consultas automatizadas (V1 no los documenta).

### Referencias (archivo:línea en V1)
- `scripts/conectores/senado.py:1-22` (formato), `:35-39` (URL, tope, columnas), `:42-46` (período), `:49-54` (cadena), `:57-73` (consulta y parseo), `:76-88` (Excel), `:91-124` (ejecución), `:127-139` (prueba manual)
- `scripts/core/http.py:4-26` · `scripts/core/registro.py:209-218` · `scripts/main.py:10,19,26-43`
- `scripts/core/almacenamiento.py:58,73-132` · `scripts/core/fuentes_urls.json:51-58` · `scripts/core/estado_descargas.json:54-59`
- `sintesis/config.yaml:203-215` · `sintesis/proyectos_ley/armar.py:33,45-77,93-122` · `sintesis/correo/armar.py:148-174`

---

## INE regional — notas previas a la ficha (0.8)
**Estado:** sin ficha. La ficha completa se hace en la fase 1, antes del conector.

- **V1 nunca leyó estos xlsx con Python:** Power Query los consolidaba en `Tabulado_INE_Regional.xlsx` y Python leía
  ese consolidado (`sintesis/lectores/base.py:139-210`). Las hojas y columnas del xlsx del INE no están documentadas en
  V1: el parser de V2 se diseña mirando los fixtures (`ingest/tests/fixtures/ine_regional/`).
- **La carpeta `AAAA-MM` de `V1/input/` es el mes de descarga, no el del dato** (inferido de los nombres): el dato va
  1–2 meses atrás. El período se toma del nombre del archivo o de su contenido.
- **Los PDF no se parseaban:** las cifras que solo salían del PDF llegaban a mano o vía GPT (`sintesis/config.yaml:15-17`).
- **Pregunta abierta — empleo:** la noticia regional del INE trae casi solo el PDF; las cifras de empleo de V1 venían
  de los cuadros estadísticos (`indicadores_principales_empleo.xlsx`, 2.ª iteración). Hay que decidir si
  `empleo_regional` vía `ine_regional` se mantiene, cambia de conector o espera a la 2.ª iteración.
