# Imagen de ingesta (fase 1, tarea 1.5). Se construye desde la raíz del repo (contexto: `.`):
#   docker compose build      (ver docker-compose.yml)
#
# Dos etapas: el "taller" instala las dependencias con uv; la "caja final" solo recibe el entorno ya armado.
# La caja final no lleva uv, ni tests, ni herramientas de construcción, ni el .env (.dockerignore).

# --- Etapa 1: taller ---
FROM python:3.13-slim AS builder
# uv en la misma versión que en local (uv --version): la imagen se arma igual que tu entorno.
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Primero solo los archivos de dependencias: si el código cambia pero uv.lock no, Docker reutiliza esta capa.
COPY pyproject.toml uv.lock ./
COPY ingest/pyproject.toml ingest/pyproject.toml
RUN uv sync --frozen --no-dev --package sintesis-ingest --no-install-workspace

# Después el código. --no-editable: el paquete queda instalado dentro de .venv (no apunta a /app/ingest/src).
COPY ingest/src ingest/src
RUN uv sync --frozen --no-dev --package sintesis-ingest --no-editable

# --- Etapa 2: caja final ---
FROM python:3.13-slim

# Usuario sin privilegios: si algo se compromete dentro del contenedor, no es root.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser
# Los datos van en /app/data (SINTESIS_LOCAL_DATA_DIR="data" por defecto); en local se monta ./data ahí.
# Las credenciales llegan como variables de entorno al correr, nunca dentro de la imagen.
ENTRYPOINT ["sintesis-ingest"]
CMD ["--help"]
