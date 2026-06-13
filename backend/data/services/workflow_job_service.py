from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.agents.orchestrator.results import summarize_steps
from backend.data.repositories import workflow_job as workflow_job_repository
from backend.schemas.workflow import (
    WorkflowJobStatusResponse,
    WorkflowJobSubmitResponse,
    WorkflowResponse,
    build_workflow_response,
)

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_FAILED = "failed"
JOB_TERMINAL_STATUSES = frozenset({JOB_STATUS_SUCCEEDED, JOB_STATUS_FAILED})


def submit_workflow_job(
    company_name: str,
    *,
    request_id: str,
) -> WorkflowJobSubmitResponse:
    """신규 워크플로우 job을 등록한다."""
    normalized_name = company_name.strip()
    if not normalized_name:
        raise ValueError("company_name은 비어 있을 수 없습니다.")

    submitted_at = _utcnow_isoformat()
    job_id = f"job-{uuid4().hex[:12]}"
    workflow_job_repository.create_workflow_job(
        job_id=job_id,
        request_id=request_id,
        company_name=normalized_name,
        status=JOB_STATUS_QUEUED,
        submitted_at=submitted_at,
        updated_at=submitted_at,
    )
    return WorkflowJobSubmitResponse(
        job_id=job_id,
        request_id=request_id,
        company_name=normalized_name,
        status=JOB_STATUS_QUEUED,
        submitted_at=submitted_at,
        status_url=f"/api/v1/workflows/jobs/{job_id}",
        result_url=f"/api/v1/workflows/jobs/{job_id}/result",
    )


def get_workflow_job_status(job_id: str) -> WorkflowJobStatusResponse | None:
    """job 상태를 API 응답 모델로 반환한다."""
    record = workflow_job_repository.get_workflow_job(job_id)
    if record is None:
        return None
    step_summary = _load_json_value(record.get("step_summary_json"))
    return WorkflowJobStatusResponse(
        job_id=str(record["job_id"]),
        request_id=str(record["request_id"]),
        company_name=str(record["company_name"]),
        status=str(record["status"]),
        submitted_at=str(record["submitted_at"]),
        started_at=_optional_str(record.get("started_at")),
        finished_at=_optional_str(record.get("finished_at")),
        error_code=_optional_str(record.get("error_code")),
        error_message=_optional_str(record.get("error_message")),
        step_summary=step_summary if isinstance(step_summary, dict) else None,
    )


def get_workflow_job_result(job_id: str) -> WorkflowResponse | None:
    """성공적으로 완료된 job의 최종 워크플로우 결과를 반환한다."""
    record = workflow_job_repository.get_workflow_job(job_id)
    if record is None or record.get("status") != JOB_STATUS_SUCCEEDED:
        return None
    result_payload = _load_json_value(record.get("result_json"))
    if not isinstance(result_payload, dict):
        return None
    return build_workflow_response(result_payload)


def get_next_queued_workflow_job() -> dict[str, Any] | None:
    """실행 대기 중인 다음 job 원본 레코드를 반환한다."""
    return workflow_job_repository.get_next_queued_workflow_job()


def claim_workflow_job(job_id: str) -> bool:
    """queued job을 running 상태로 전환한다."""
    timestamp = _utcnow_isoformat()
    return workflow_job_repository.claim_workflow_job(
        job_id=job_id,
        started_at=timestamp,
        updated_at=timestamp,
    )


def complete_workflow_job(job_id: str, result_payload: dict[str, Any]) -> None:
    """성공한 워크플로우 결과를 저장하고 job을 완료 처리한다."""
    workflow_response = build_workflow_response(result_payload)
    serialized_result = workflow_response.model_dump(mode="json", exclude_none=True)
    step_summary = summarize_steps(serialized_result["steps"])
    timestamp = _utcnow_isoformat()
    workflow_job_repository.complete_workflow_job(
        job_id=job_id,
        result_json=json.dumps(serialized_result, ensure_ascii=False),
        step_summary_json=json.dumps(step_summary, ensure_ascii=False),
        finished_at=timestamp,
        updated_at=timestamp,
    )


def fail_workflow_job(
    job_id: str,
    *,
    error_code: str,
    error_message: str,
) -> None:
    """실패한 워크플로우 job의 오류를 저장한다."""
    timestamp = _utcnow_isoformat()
    workflow_job_repository.fail_workflow_job(
        job_id=job_id,
        error_code=error_code,
        error_message=error_message,
        finished_at=timestamp,
        updated_at=timestamp,
    )


def requeue_incomplete_workflow_jobs() -> int:
    """미완료 상태로 남은 job을 재실행 대기 상태로 되돌린다."""
    return workflow_job_repository.requeue_incomplete_workflow_jobs(
        updated_at=_utcnow_isoformat()
    )


def _utcnow_isoformat() -> str:
    return datetime.now(UTC).isoformat()


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _load_json_value(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(str(value))
