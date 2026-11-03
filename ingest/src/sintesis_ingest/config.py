"""Configuración de ejecución (variables de entorno) y catálogo de fuentes (sources.yaml)."""

from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
Email = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class Settings(BaseSettings):
    """Lo que cambia por máquina o entorno. Se lee de variables SINTESIS_*.

    En local también lee `.env` (en el directorio actual): las credenciales quedan dentro del proceso, sin
    exportarlas en la terminal. Las variables de entorno tienen prioridad (así llegan en Cloud Run).
    """

    # hide_input_in_errors: si un campo falla, el error no muestra los valores de los demás (credenciales).
    model_config = SettingsConfigDict(
        env_prefix="SINTESIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    env: Literal["local", "dev", "prod"] = "local"
    storage_backend: Literal["local", "gcs"] = "local"
    local_data_dir: Path = Path("data")
    gcs_bucket: str | None = None
    contact_email: Email  # va en el User-Agent: sin valor por defecto a propósito
    request_pause_seconds: float = Field(default=2.0, ge=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def _gcs_needs_bucket(self) -> "Settings":
        if self.storage_backend == "gcs" and not self.gcs_bucket:
            raise ValueError("SINTESIS_GCS_BUCKET es obligatoria cuando SINTESIS_STORAGE_BACKEND=gcs")
        return self


class _Source(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: SourceId
    name: NonEmptyStr
    enabled: bool = True


class IneRegionalSource(_Source):
    """Boletín regional del INE, encontrado por palabra clave en la API de noticias."""

    connector: Literal["ine_regional"]
    region: int = Field(ge=1, le=16)
    keyword: NonEmptyStr
    file_names: dict[Literal["xlsx", "pdf"], NonEmptyStr] = Field(default_factory=dict)


class SenadoSource(_Source):
    """Consulta avanzada de tramitacion.senado.cl (ver docs/fuentes.md)."""

    connector: Literal["senado"]
    status: Literal["T", "L"]  # T en tramitación · L publicado como ley
    date_field: Literal["ingreso", "publicacion"]


Source = Annotated[IneRegionalSource | SenadoSource, Field(discriminator="connector")]


class SourceCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sources: list[Source] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "SourceCatalog":
        ids = [s.id for s in self.sources]
        duplicated = sorted({i for i in ids if ids.count(i) > 1})
        if duplicated:
            raise ValueError(f"ids duplicados: {', '.join(duplicated)}")
        return self


class SourcesConfigError(ValueError):
    """sources.yaml inválido. El mensaje indica la fuente (posición e id) y el campo."""


def load_sources(path: Path | None = None) -> SourceCatalog:
    """Carga y valida el catálogo. Sin `path`, usa el sources.yaml incluido en el paquete."""
    if path is None:
        text = files("sintesis_ingest").joinpath("sources.yaml").read_text(encoding="utf-8")
    else:
        text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    try:
        return SourceCatalog.model_validate(data)
    except ValidationError as e:
        raise SourcesConfigError(_describe(e, data)) from e


def _describe(error: ValidationError, data: object) -> str:
    raw = data.get("sources") if isinstance(data, dict) else None
    lines = ["sources.yaml inválido:"]
    for err in error.errors():
        loc = list(err["loc"])
        where = "catálogo"
        if len(loc) >= 2 and loc[0] == "sources" and isinstance(loc[1], int):
            index = loc[1]
            item = raw[index] if isinstance(raw, list) and index < len(raw) else None
            source_id = item.get("id", "?") if isinstance(item, dict) else "?"
            where = f"sources[{index}] (id={source_id})"
            loc = loc[3:] if len(loc) > 2 and loc[2] in ("ine_regional", "senado") else loc[2:]
        field = ".".join(str(p) for p in loc) or "-"
        lines.append(f"  {where} → {field}: {err['msg']}")
    return "\n".join(lines)
