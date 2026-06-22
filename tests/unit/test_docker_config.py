from __future__ import annotations

from pathlib import Path

import yaml

from frontend.config import DEFAULT_BACKEND_URL, get_backend_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_frontend_backend_url_defaults_to_localhost(monkeypatch) -> None:
    monkeypatch.delenv("FINAGENT_BACKEND_URL", raising=False)

    assert get_backend_url() == DEFAULT_BACKEND_URL


def test_frontend_backend_url_uses_container_environment(monkeypatch) -> None:
    monkeypatch.setenv("FINAGENT_BACKEND_URL", "http://backend:8000/")

    assert get_backend_url() == "http://backend:8000"


def test_compose_defines_database_and_application_services() -> None:
    compose_path = PROJECT_ROOT / "backend" / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose["services"]

    assert set(services) == {"postgres", "backend", "frontend"}
    assert services["backend"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"
    assert (
        services["frontend"]["environment"]["FINAGENT_BACKEND_URL"]
        == "http://backend:8000"
    )
    assert services["backend"]["build"]["dockerfile"] == "backend/Dockerfile"
    assert services["frontend"]["build"]["dockerfile"] == "frontend/Dockerfile"


def test_dockerfiles_run_as_non_root_with_healthchecks() -> None:
    for relative_path in ("backend/Dockerfile", "frontend/Dockerfile"):
        content = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

        assert "FROM python:3.13-slim" in content
        assert "USER appuser" in content
        assert "HEALTHCHECK" in content


def test_backend_dockerfile_installs_cpu_only_torch() -> None:
    content = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "https://download.pytorch.org/whl/cpu" in content
    assert "TORCH_VERSION=2.12.1+cpu" in content
