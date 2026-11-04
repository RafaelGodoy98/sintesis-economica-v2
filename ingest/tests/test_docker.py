"""Barreras de la imagen que se comprueban sin Docker (la imagen real se verifica con docker en la 1.5)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [x.strip() for x in text.splitlines() if x.strip() and not x.startswith("#")]


def test_dockerignore_is_an_allowlist_without_secrets_or_data():
    rules = lines(ROOT / ".dockerignore")
    assert rules[0] == "*"  # todo excluido por defecto
    allowed = [r for r in rules if r.startswith("!")]
    assert not any(".env" in r or "data" in r or "tests" in r for r in allowed)
    assert "**/.env" in rules and "**/.env.*" in rules


def test_final_image_runs_as_non_root_user():
    dockerfile = (ROOT / "ingest" / "Dockerfile").read_text(encoding="utf-8")
    final_stage = dockerfile.split("FROM python:3.13-slim\n")[-1]
    assert "USER appuser" in final_stage
    assert "COPY --from=builder /app/.venv" in final_stage
    assert "uv" not in final_stage.replace(".venv", "")  # la caja final no lleva uv


def test_compose_injects_credentials_at_runtime_not_build():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "env_file: .env" in compose
    assert "${DATA_DIR:-./data}:/app/data" in compose
