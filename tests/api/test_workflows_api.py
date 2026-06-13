import importlib
import logging

import pytest
from fastapi.testclient import TestClient


def _load_modules() -> tuple[object, object]:
    main_module = importlib.import_module("backend.main")
    workflows_module = importlib.import_module("backend.api.routes.workflows")
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
    async def fake_run_credit_workflow(
        company_name: str,
        *,
        extra_payload: dict[str, str] | None = None,
    ) -> dict[str, str]:
        return {"status": "success", "company_name": company_name}

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    response = client.post(
        "/api/v1/workflows/credit-assessment",
        json={"company_name": "FinAgent"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["company_name"] == "FinAgent"
    assert payload["context"]["company_name"] == "FinAgent"
    assert payload["context"]["request_id"] == payload["request_id"]
    assert payload["steps"] == []
    assert payload["request_id"].startswith("req-")
    assert response.headers["x-request-id"] == payload["request_id"]


def test_orchestrator_route_runs_orchestrator(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_credit_workflow(
        company_name: str,
        *,
        extra_payload: dict[str, str] | None = None,
    ) -> dict[str, str]:
        return {"status": "success", "company_name": company_name}

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    response = client.post(
        "/api/v1/workflows/orchestrator",
        json={"company_name": "FinAgent"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["company_name"] == "FinAgent"
    assert payload["context"]["company_name"] == "FinAgent"
    assert payload["context"]["request_id"] == payload["request_id"]
    assert payload["steps"] == []
    assert payload["request_id"].startswith("req-")
    assert response.headers["x-request-id"] == payload["request_id"]


def test_orchestrator_route_logs_request_and_completion(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_run_credit_workflow(
        company_name: str,
        *,
        extra_payload: dict[str, str] | None = None,
    ) -> dict[str, str]:
        return {"status": "success", "company_name": company_name}

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    with caplog.at_level(logging.INFO, logger="backend.api.routes.workflows"):
        response = client.post(
            "/api/v1/workflows/orchestrator",
            json={"company_name": "FinAgent"},
        )

    assert response.status_code == 200
    request_ids = [record.request_id for record in caplog.records]
    messages = [record.message for record in caplog.records]
    assert any(request_id.startswith("req-") for request_id in request_ids)
    assert any(
        "credit_workflow_requested company_name=FinAgent" in msg
        for msg in messages
    )
    assert any(
        (
            "credit_workflow_completed company_name=FinAgent status=success" in msg
        )
        for msg in messages
    )


def test_orchestrator_route_returns_400_for_normalized_empty_company_name(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_credit_workflow(
        company_name: str,
        *,
        extra_payload: dict[str, str] | None = None,
    ) -> dict[str, str]:
        raise ValueError("company_name은 비어 있을 수 없습니다.")

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    response = client.post(
        "/api/v1/workflows/orchestrator",
        json={"company_name": "   "},
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_INPUT",
        "message": "입력값이 올바르지 않습니다.",
        "detail": {"company_name": "   "},
        "request_id": response.json()["request_id"],
    }
    assert response.json()["request_id"].startswith("req-")
    assert response.headers["x-request-id"] == response.json()["request_id"]


def test_orchestrator_route_returns_500_when_orchestrator_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_credit_workflow(
        company_name: str,
        *,
        extra_payload: dict[str, str] | None = None,
    ) -> dict[str, str]:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(workflows, "run_credit_workflow", fake_run_credit_workflow)

    response = client.post(
        "/api/v1/workflows/orchestrator",
        json={"company_name": "FinAgent"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "code": "AGENT_EXECUTION_FAILED",
        "message": "오케스트레이터 실행 중 오류가 발생했습니다.",
        "detail": {"company_name": "FinAgent"},
        "request_id": response.json()["request_id"],
    }
    assert response.json()["request_id"].startswith("req-")
    assert response.headers["x-request-id"] == response.json()["request_id"]
