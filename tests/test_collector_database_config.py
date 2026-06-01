from pathlib import Path

import backend_env
import pytest
from agents.company_registry.tools import get_env_path, resolve_database_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clear_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in (
        "DATABASE_URL",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    ):
        monkeypatch.delenv(env_name, raising=False)


def test_get_backend_env_path_prefers_backend_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend_env_path = tmp_path / "backend.env"
    legacy_env_path = tmp_path / "legacy.env"
    backend_env_path.write_text("OPEN_DART_API_KEY=test\n", encoding="utf-8")

    monkeypatch.setattr(backend_env, "DEFAULT_ENV_PATH", backend_env_path)
    monkeypatch.setattr(backend_env, "LEGACY_ENV_PATH", legacy_env_path)

    assert backend_env.get_backend_env_path() == backend_env_path


def test_get_backend_env_path_falls_back_to_legacy_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend_env_path = tmp_path / "backend.env"
    legacy_env_path = tmp_path / "legacy.env"
    legacy_env_path.write_text("OPEN_DART_API_KEY=test\n", encoding="utf-8")

    monkeypatch.setattr(backend_env, "DEFAULT_ENV_PATH", backend_env_path)
    monkeypatch.setattr(backend_env, "LEGACY_ENV_PATH", legacy_env_path)

    assert backend_env.get_backend_env_path() == legacy_env_path


def test_get_env_path_defaults_to_backend_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected_path = tmp_path / "backend.env"
    expected_path.write_text("OPEN_DART_API_KEY=test\n", encoding="utf-8")

    monkeypatch.setattr(backend_env, "DEFAULT_ENV_PATH", expected_path)
    monkeypatch.setattr(backend_env, "LEGACY_ENV_PATH", PROJECT_ROOT / "backend" / "agents" / ".env")

    assert get_env_path(None) == expected_path


def test_resolve_database_url_prefers_explicit_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql+psycopg2://user:pass@localhost:5432/customdb"

    monkeypatch.setenv("DATABASE_URL", database_url)

    assert resolve_database_url() == database_url


def test_resolve_database_url_builds_url_from_postgres_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "finagent")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss word")
    monkeypatch.setenv("POSTGRES_DB", "finagent_dev")

    assert (
        resolve_database_url()
        == "postgresql+psycopg2://finagent:p%40ss+word@127.0.0.1:5433/finagent_dev"
    )


def test_resolve_database_url_requires_credentials() -> None:
    with pytest.raises(ValueError, match="PostgreSQL 연결 정보를 찾지 못했습니다"):
        resolve_database_url()
