import importlib
import logging

import pytest
from fastapi.testclient import TestClient


def _load_modules() -> tuple[object, object]:
    main_module = importlib.import_module("main")
    workflows_module = importlib.import_module("api.routes.workflows")
    return main_module, workflows_module


main_module, workflows = _load_modules()
app = main_module.app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_credit_assessment_route_runs_orchestrator(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_credit_workflow(company_name: str) -> dict[str, str]:
        return {"status": "success", "company_name": company_name}

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    response = client.post(
        "/api/v1/workflows/credit-assessment",
        json={"company_name": "FinAgent"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "company_name": "FinAgent"}


def test_orchestrator_route_runs_orchestrator(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_credit_workflow(company_name: str) -> dict[str, str]:
        return {"status": "success", "company_name": company_name}

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    response = client.post(
        "/api/v1/workflows/orchestrator",
        json={"company_name": "FinAgent"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "company_name": "FinAgent"}


def test_orchestrator_route_logs_request_and_completion(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_run_credit_workflow(company_name: str) -> dict[str, str]:
        return {"status": "success", "company_name": company_name}

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    with caplog.at_level(logging.INFO, logger="api.routes.workflows"):
        response = client.post(
            "/api/v1/workflows/orchestrator",
            json={"company_name": "FinAgent"},
        )

    assert response.status_code == 200
    messages = [record.message for record in caplog.records]
    assert any(
        "credit_workflow_requested company_name=FinAgent" in msg
        for msg in messages
    )
    assert any(
        "credit_workflow_completed company_name=FinAgent status=success" in msg
        for msg in messages
    )


def test_orchestrator_route_returns_400_for_normalized_empty_company_name(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_credit_workflow(company_name: str) -> dict[str, str]:
        raise ValueError("company_name은 비어 있을 수 없습니다.")

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    response = client.post(
        "/api/v1/workflows/orchestrator",
        json={"company_name": "   "},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "code": "INVALID_INPUT",
            "message": "입력값이 올바르지 않습니다.",
            "detail": {"company_name": "   "},
        }
    }


def test_orchestrator_route_returns_500_when_orchestrator_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_credit_workflow(company_name: str) -> dict[str, str]:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    response = client.post(
        "/api/v1/workflows/orchestrator",
        json={"company_name": "FinAgent"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "AGENT_EXECUTION_FAILED",
            "message": "오케스트레이터 실행 중 오류가 발생했습니다.",
            "detail": {"company_name": "FinAgent"},
        }
    }
