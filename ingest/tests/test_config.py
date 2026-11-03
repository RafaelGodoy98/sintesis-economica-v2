from pathlib import Path

import pytest
from pydantic import ValidationError

from sintesis_ingest.config import Settings, SourcesConfigError, load_sources

VALID_SOURCE = """
  - id: empleo_regional
    name: Empleo Regional
    connector: ine_regional
    region: 5
    keyword: empleo
"""


def write_catalog(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text("sources:" + body, encoding="utf-8")
    return path


# --- sources.yaml ---


def test_packaged_catalog_loads():
    catalog = load_sources()
    ids = [s.id for s in catalog.sources]
    assert "empleo_regional" in ids
    assert "senado_proyectos_tramitacion" in ids
    assert len(ids) == len(set(ids))


def test_duplicated_id_fails(tmp_path):
    path = write_catalog(tmp_path, VALID_SOURCE + VALID_SOURCE)
    with pytest.raises(SourcesConfigError, match="ids duplicados: empleo_regional"):
        load_sources(path)


def test_unknown_connector_fails(tmp_path):
    body = """
  - id: uf
    name: UF
    connector: bcentral_magic
"""
    with pytest.raises(SourcesConfigError, match=r"sources\[0\] \(id=uf\)"):
        load_sources(write_catalog(tmp_path, body))


def test_misspelled_field_fails_and_names_source_and_field(tmp_path):
    body = VALID_SOURCE.replace("keyword: empleo", "keyword: empleo\n    keywrod: typo")
    with pytest.raises(SourcesConfigError) as exc:
        load_sources(write_catalog(tmp_path, body))
    assert "sources[0] (id=empleo_regional) → keywrod" in str(exc.value)


def test_field_from_another_connector_fails(tmp_path):
    body = VALID_SOURCE + "    status: T\n"
    with pytest.raises(SourcesConfigError, match="→ status"):
        load_sources(write_catalog(tmp_path, body))


def test_missing_required_field_fails(tmp_path):
    body = VALID_SOURCE.replace("    keyword: empleo\n", "")
    with pytest.raises(SourcesConfigError, match="→ keyword"):
        load_sources(write_catalog(tmp_path, body))


def test_blank_keyword_fails(tmp_path):
    body = VALID_SOURCE.replace("keyword: empleo", "keyword: '   '")
    with pytest.raises(SourcesConfigError, match="→ keyword"):
        load_sources(write_catalog(tmp_path, body))


def test_non_snake_case_id_fails(tmp_path):
    body = VALID_SOURCE.replace("id: empleo_regional", "id: Empleo-Regional")
    with pytest.raises(SourcesConfigError, match="→ id"):
        load_sources(write_catalog(tmp_path, body))


# --- Settings (variables de entorno) ---


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Sin variables SINTESIS_* y en un directorio vacío: los tests nunca leen el .env real."""
    for name in ("ENV", "STORAGE_BACKEND", "LOCAL_DATA_DIR", "GCS_BUCKET", "CONTACT_EMAIL", "LOG_LEVEL"):
        monkeypatch.delenv(f"SINTESIS_{name}", raising=False)
    monkeypatch.chdir(tmp_path)
    return monkeypatch


def test_settings_require_contact_email(clean_env):
    with pytest.raises(ValidationError, match="contact_email"):
        Settings()


def test_settings_defaults(clean_env):
    clean_env.setenv("SINTESIS_CONTACT_EMAIL", "dev@example.com")
    settings = Settings()
    assert settings.env == "local"
    assert settings.storage_backend == "local"
    assert settings.request_pause_seconds == 2.0


def test_gcs_backend_requires_bucket(clean_env):
    clean_env.setenv("SINTESIS_CONTACT_EMAIL", "dev@example.com")
    clean_env.setenv("SINTESIS_STORAGE_BACKEND", "gcs")
    with pytest.raises(ValidationError, match="SINTESIS_GCS_BUCKET"):
        Settings()


def test_settings_read_from_env(clean_env):
    clean_env.setenv("SINTESIS_CONTACT_EMAIL", "dev@example.com")
    clean_env.setenv("SINTESIS_STORAGE_BACKEND", "gcs")
    clean_env.setenv("SINTESIS_GCS_BUCKET", "my-bucket")
    clean_env.setenv("SINTESIS_ENV", "dev")
    settings = Settings()
    assert (settings.env, settings.gcs_bucket) == ("dev", "my-bucket")


def test_settings_read_dotenv_and_env_wins(clean_env, tmp_path):
    (tmp_path / ".env").write_text(
        "SINTESIS_CONTACT_EMAIL=file@example.com\nSINTESIS_ENV=dev\n", encoding="utf-8"
    )
    clean_env.setenv("SINTESIS_ENV", "prod")
    settings = Settings()
    assert settings.contact_email == "file@example.com"  # viene del .env
    assert settings.env == "prod"  # la variable de entorno le gana al archivo
