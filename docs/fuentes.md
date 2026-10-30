# Fichas de fuentes

Una ficha describe cómo V1 obtiene, parsea y valida una fuente, para portarla a V2 sin copiar código.
La redacta el subagente `v1-analista` (solo lectura sobre V1), Claude la contrasta con el código y Rafael la valida.
Recién con la ficha validada se planifica el conector de V2. Rutas citadas: relativas a V1.

| Fuente | `source_id` | Estado |
|---|---|---|
| Senado — proyectos de ley | `senado_bills` | Borrador, pendiente de validación |

---

## Senado de Chile — proyectos de ley (`senado_bills`)
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
