import importlib

import pytest
from fastapi.testclient import TestClient

from backend.schemas.workflow import (
    WorkflowJobStatusResponse,
    WorkflowJobSubmitResponse,
    build_workflow_response,
)


def _load_modules() -> tuple[object, object]:
    main_module = importlib.import_module("backend.main")
    workflows_module = importlib.import_module("backend.api.routes.workflows")
    return main_module, workflows_module


main_module, workflows = _load_modules()
app = main_module.app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_submit_workflow_job_returns_202(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_submit_workflow_job(
        company_name: str,
        *,
        request_id: str,
    ) -> WorkflowJobSubmitResponse:
        return WorkflowJobSubmitResponse(
            job_id="job-123",
            request_id=request_id,
            company_name=company_name,
            status="queued",
            submitted_at="2026-06-13T00:00:00+00:00",
            status_url="/api/v1/workflows/jobs/job-123",
            result_url="/api/v1/workflows/jobs/job-123/result",
        )

    monkeypatch.setattr(workflows, "submit_workflow_job", fake_submit_workflow_job)
    monkeypatch.setattr(
        workflows.workflow_job_runner,
        "notify_job_submitted",
        lambda: None,
    )

    response = client.post("/api/v1/workflows/jobs", json={"company_name": "FinAgent"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"] == "job-123"
    assert payload["status"] == "queued"
    assert payload["company_name"] == "FinAgent"
    assert payload["request_id"].startswith("req-")


def test_get_workflow_job_status_returns_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "get_workflow_job_status",
        lambda job_id: WorkflowJobStatusResponse(
            job_id=job_id,
            request_id="req-123",
            company_name="FinAgent",
            status="running",
            submitted_at="2026-06-13T00:00:00+00:00",
            started_at="2026-06-13T00:00:01+00:00",
        ),
    )

    response = client.get("/api/v1/workflows/jobs/job-123")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert "error_message" not in response.json()


def test_get_workflow_job_status_returns_public_failure_message_only(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "get_workflow_job_status",
        lambda job_id: WorkflowJobStatusResponse(
            job_id=job_id,
            request_id="req-123",
            company_name="FinAgent",
            status="failed",
            submitted_at="2026-06-13T00:00:00+00:00",
            finished_at="2026-06-13T00:00:03+00:00",
            error_code="AGENT_EXECUTION_FAILED",
            message="심사 워크플로우 실행 중 오류가 발생했습니다.",
        ),
    )

    response = client.get("/api/v1/workflows/jobs/job-123")

    assert response.status_code == 200
    assert response.json()["error_code"] == "AGENT_EXECUTION_FAILED"
    assert (
        response.json()["message"]
        == "심사 워크플로우 실행 중 오류가 발생했습니다."
    )
    assert "error_message" not in response.json()


def test_get_workflow_job_status_returns_404_when_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflows, "get_workflow_job_status", lambda job_id: None)

    response = client.get("/api/v1/workflows/jobs/job-missing")

    assert response.status_code == 404
    assert response.json()["code"] == "JOB_NOT_FOUND"


def test_stream_workflow_job_status_emits_progress_events(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses = [
        WorkflowJobStatusResponse(
            job_id="job-123",
            request_id="req-123",
            company_name="FinAgent",
            status="running",
            submitted_at="2026-06-13T00:00:00+00:00",
            started_at="2026-06-13T00:00:01+00:00",
        ),
        WorkflowJobStatusResponse(
            job_id="job-123",
            request_id="req-123",
            company_name="FinAgent",
            status="running",
            submitted_at="2026-06-13T00:00:00+00:00",
            started_at="2026-06-13T00:00:01+00:00",
            step_summary={
                "success": 1,
                "partial": 0,
                "failed": 0,
                "fallback": 0,
                "completed": 1,
            },
        ),
        WorkflowJobStatusResponse(
            job_id="job-123",
            request_id="req-123",
            company_name="FinAgent",
            status="succeeded",
            submitted_at="2026-06-13T00:00:00+00:00",
            started_at="2026-06-13T00:00:01+00:00",
            finished_at="2026-06-13T00:00:03+00:00",
            step_summary={
                "success": 2,
                "partial": 0,
                "failed": 0,
                "fallback": 0,
                "completed": 2,
            },
        ),
    ]

    def fake_get_workflow_job_status(job_id: str) -> WorkflowJobStatusResponse | None:
        return statuses.pop(0)

    monkeypatch.setattr(workflows, "SSE_POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(
        workflows,
        "get_workflow_job_status",
        fake_get_workflow_job_status,
    )

    with client.stream("GET", "/api/v1/workflows/jobs/job-123/stream") as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: running" in body
    assert "event: progress" in body
    assert "event: complete" in body
    assert '"step_summary": {"success": 2' in body


def test_stream_workflow_job_status_returns_404_when_missing(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflows, "get_workflow_job_status", lambda job_id: None)

    response = client.get("/api/v1/workflows/jobs/job-missing/stream")

    assert response.status_code == 404
    assert response.json()["code"] == "JOB_NOT_FOUND"


def test_get_workflow_job_result_returns_409_until_completed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "get_workflow_job_status",
        lambda job_id: WorkflowJobStatusResponse(
            job_id=job_id,
            request_id="req-123",
            company_name="FinAgent",
            status="running",
            submitted_at="2026-06-13T00:00:00+00:00",
        ),
    )

    response = client.get("/api/v1/workflows/jobs/job-123/result")

    assert response.status_code == 409
    assert response.json()["code"] == "JOB_NOT_COMPLETED"


def test_get_workflow_job_result_returns_workflow_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "get_workflow_job_status",
        lambda job_id: WorkflowJobStatusResponse(
            job_id=job_id,
            request_id="req-123",
            company_name="FinAgent",
            status="succeeded",
            submitted_at="2026-06-13T00:00:00+00:00",
            finished_at="2026-06-13T00:00:03+00:00",
        ),
    )
    monkeypatch.setattr(
        workflows,
        "get_workflow_job_result",
        lambda job_id: build_workflow_response(
            {
                "request_id": "req-123",
                "company_name": "FinAgent",
                "status": "success",
                "context": {},
                "steps": [],
            }
        ),
    )

    response = client.get("/api/v1/workflows/jobs/job-123/result")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["company_name"] == "FinAgent"
