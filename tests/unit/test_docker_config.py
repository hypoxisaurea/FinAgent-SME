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


def test_streamlit_navigation_chrome_is_hidden() -> None:
    content = (PROJECT_ROOT / "frontend" / "streamlit_ui.py").read_text(
        encoding="utf-8"
    )

    assert 'header[data-testid="stHeader"]' in content
    assert '[data-testid="stToolbar"]' in content
    assert "#MainMenu" in content
    assert '[data-testid="stSidebarNav"]' in content


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
    assert all("container_name" not in service for service in services.values())


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


def test_docker_smoke_script_exercises_compose_healthchecks() -> None:
    content = (PROJECT_ROOT / "scripts" / "docker-smoke.sh").read_text(
        encoding="utf-8"
    )

    assert "docker compose" in content
    assert "up --build -d" in content
    assert "/api/health" in content
    assert "/_stcore/health" in content
    assert "artifacts/docker_smoke_verification.json" in content
    assert "docker_smoke_passed" in content
    assert "docker_smoke_evidence" in content


def test_stack_database_status_uses_compose_service_container() -> None:
    content = (PROJECT_ROOT / "scripts" / "lib" / "stack.sh").read_text(
        encoding="utf-8"
    )

    assert 'STACK_POSTGRES_SERVICE_NAME="postgres"' in content
    assert 'ps -q "$STACK_POSTGRES_SERVICE_NAME"' in content
    assert "finagent-postgres" not in content


def test_stack_database_stop_skips_when_docker_is_unavailable() -> None:
    content = (PROJECT_ROOT / "scripts" / "lib" / "stack.sh").read_text(
        encoding="utf-8"
    )

    assert "Skipping backend PostgreSQL stop because Docker is unavailable" in content
    assert "stack_stop_database() {" in content
    assert "if ! stack_can_manage_database; then" in content


def test_docker_smoke_workflow_runs_script() -> None:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "docker-smoke.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["docker-smoke"]["steps"]

    assert workflow["name"] == "Docker Smoke"
    assert "workflow_dispatch" in workflow[True]
    assert any(step.get("run") == "./scripts/docker-smoke.sh" for step in steps)
    assert any(
        step.get("uses") == "actions/upload-artifact@v4"
        and step.get("with", {}).get("name") == "docker-smoke-verification"
        and step.get("with", {}).get("path")
        == "artifacts/docker_smoke_verification.json"
        for step in steps
    )
