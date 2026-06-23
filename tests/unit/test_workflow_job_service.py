from __future__ import annotations

from backend.data.services import workflow_job_service


def test_get_workflow_job_status_exposes_public_message_only(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow_job_service.workflow_job_repository,
        "get_workflow_job",
        lambda job_id: {
            "job_id": job_id,
            "request_id": "req-123",
            "company_name": "FinAgent",
            "status": workflow_job_service.JOB_STATUS_FAILED,
            "submitted_at": "2026-06-19T00:00:00+00:00",
            "started_at": "2026-06-19T00:00:01+00:00",
            "finished_at": "2026-06-19T00:00:03+00:00",
            "error_code": "AGENT_EXECUTION_FAILED",
            "error_message": "traceback-like internal detail",
            "step_summary_json": None,
        },
    )

    response = workflow_job_service.get_workflow_job_status("job-123")

    assert response is not None
    assert response.error_code == "AGENT_EXECUTION_FAILED"
    assert response.message == "심사 워크플로우 실행 중 오류가 발생했습니다."
    assert "error_message" not in response.model_dump(mode="json")


def test_get_workflow_job_status_uses_generic_message_for_unknown_error_code(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow_job_service.workflow_job_repository,
        "get_workflow_job",
        lambda job_id: {
            "job_id": job_id,
            "request_id": "req-123",
            "company_name": "FinAgent",
            "status": workflow_job_service.JOB_STATUS_FAILED,
            "submitted_at": "2026-06-19T00:00:00+00:00",
            "started_at": None,
            "finished_at": "2026-06-19T00:00:03+00:00",
            "error_code": "UNKNOWN_FAILURE",
            "error_message": "sensitive internal detail",
            "step_summary_json": None,
        },
    )

    response = workflow_job_service.get_workflow_job_status("job-456")

    assert response is not None
    assert response.message == "워크플로우 job이 실패했습니다."


def test_get_workflow_job_status_exposes_restart_failure_message(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        workflow_job_service.workflow_job_repository,
        "get_workflow_job",
        lambda job_id: {
            "job_id": job_id,
            "request_id": "req-789",
            "company_name": "FinAgent",
            "status": workflow_job_service.JOB_STATUS_FAILED,
            "submitted_at": "2026-06-19T00:00:00+00:00",
            "started_at": None,
            "finished_at": "2026-06-19T00:00:03+00:00",
            "error_code": "WORKER_RESTARTED",
            "error_message": "workflow job interrupted by server restart",
            "step_summary_json": None,
        },
    )

    response = workflow_job_service.get_workflow_job_status("job-789")

    assert response is not None
    assert (
        response.message
        == "서버 재시작으로 이전 작업이 종료되었습니다. 다시 시도해주세요."
    )


def test_update_workflow_job_progress_stores_step_summary(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_update_workflow_job_progress(
        *,
        job_id: str,
        step_summary_json: str,
        updated_at: str,
    ) -> None:
        captured["job_id"] = job_id
        captured["step_summary_json"] = step_summary_json
        captured["updated_at"] = updated_at

    monkeypatch.setattr(
        workflow_job_service.workflow_job_repository,
        "update_workflow_job_progress",
        fake_update_workflow_job_progress,
    )

    workflow_job_service.update_workflow_job_progress(
        "job-123",
        [
            {
                "agent_name": "news_collector",
                "status": "success",
                "fallback_used": False,
            },
            {
                "agent_name": "industry_analyst",
                "status": "partial",
                "fallback_used": True,
            },
        ],
    )

    assert captured["job_id"] == "job-123"
    assert '"success": 1' in captured["step_summary_json"]
    assert '"partial": 1' in captured["step_summary_json"]
    assert '"fallback": 1' in captured["step_summary_json"]
    assert '"completed": 2' in captured["step_summary_json"]
    assert captured["updated_at"]
