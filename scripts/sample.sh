#!/usr/bin/env bash
# Baja una muestra de BigQuery a CSV para revisarla en Excel (2.5).
#   TABLE=marts.dim_series [LIMIT=100]  → SELECT * FROM la tabla LIMIT n
#   SQL=ruta/consulta.sql [LIMIT=100]   → la consulta del archivo (LIMIT solo corta las filas que se escriben)
# Primero un dry-run (cuánto leería, sin ejecutar ni cobrar); después la consulta. Salida: $DATA_DIR/samples/<nombre>.csv
set -euo pipefail

TABLE="${TABLE:-}"
SQL="${SQL:-}"
LIMIT="${LIMIT:-100}"
OUT_DIR="${DATA_DIR:-./data}/samples"

fail() { echo "make sample: $1" >&2; exit 2; }

if [[ -n "$TABLE" && -n "$SQL" ]]; then fail "usa TABLE o SQL, no ambos"; fi
if [[ ! "$LIMIT" =~ ^[0-9]+$ ]]; then fail "LIMIT debe ser un número entero; llegó: $LIMIT"; fi

if [[ -n "$TABLE" ]]; then
  # Solo dataset.tabla: evita que TABLE meta SQL arbitrario en la consulta.
  [[ "$TABLE" =~ ^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$ ]] || fail "TABLE debe tener la forma dataset.tabla; llegó: $TABLE"
  query="SELECT * FROM \`$TABLE\` LIMIT $LIMIT"
  name="$TABLE"
elif [[ -n "$SQL" ]]; then
  [[ -f "$SQL" ]] || fail "no existe el archivo SQL: $SQL"
  query="$(cat "$SQL")"
  name="$(basename "$SQL" .sql)"
else
  fail "falta TABLE o SQL. Ej.: make sample TABLE=marts.dim_series LIMIT=100"
fi

project_flag=()
if [[ -n "${SINTESIS_GCP_PROJECT:-}" ]]; then project_flag=(--project_id="$SINTESIS_GCP_PROJECT"); fi

echo "Dry-run (no ejecuta ni cobra):"
bq -q "${project_flag[@]}" query --use_legacy_sql=false --dry_run "$query"

mkdir -p "$OUT_DIR"
out="$OUT_DIR/$name.csv"
# BOM UTF-8 al inicio: así Excel reconoce la codificación y muestra bien los acentos ("índice").
printf '\xEF\xBB\xBF' > "$out"
bq -q "${project_flag[@]}" query --use_legacy_sql=false --format=csv --max_rows="$LIMIT" "$query" >> "$out"
echo "Escrito: $out ($(($(wc -l < "$out") - 1)) filas)"
