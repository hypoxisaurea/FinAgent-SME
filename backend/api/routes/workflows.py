import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from backend.agents.orchestrator.orchestrator import run_credit_workflow
from backend.common.logging import get_request_id
from backend.data.services.workflow_job_runner import workflow_job_runner
from backend.data.services.workflow_job_service import (
    JOB_STATUS_FAILED,
    JOB_STATUS_SUCCEEDED,
    get_workflow_job_result,
    get_workflow_job_status,
    submit_workflow_job,
)
from backend.schemas.credit import CreditAssessmentRequest
from backend.schemas.workflow import (
    WorkflowErrorResponse,
    WorkflowJobStatusResponse,
    WorkflowJobSubmitResponse,
    WorkflowResponse,
    build_workflow_error_response,
    build_workflow_response,
)
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])
logger = logging.getLogger(__name__)
SSE_POLL_INTERVAL_SECONDS = 1.0


WORKFLOW_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": WorkflowErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": WorkflowErrorResponse},
    status.HTTP_409_CONFLICT: {"model": WorkflowErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": WorkflowErrorResponse},
}


@router.post(
    "/credit-assessment",
    response_model=WorkflowResponse,
    responses=WORKFLOW_ERROR_RESPONSES,
)
async def credit_assessment(
    body: CreditAssessmentRequest,
) -> WorkflowResponse | JSONResponse:
    return await _execute_credit_workflow(body)


@router.post(
    "/orchestrator",
    response_model=WorkflowResponse,
    responses=WORKFLOW_ERROR_RESPONSES,
)
async def credit_assessment_orchestrator(
    body: CreditAssessmentRequest,
) -> WorkflowResponse | JSONResponse:
    return await _execute_credit_workflow(body)


@router.post(
    "/jobs",
    response_model=WorkflowJobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=WORKFLOW_ERROR_RESPONSES,
)
async def submit_credit_assessment_job(
    body: CreditAssessmentRequest,
) -> WorkflowJobSubmitResponse | JSONResponse:
    request_id = get_request_id()
    try:
        logger.info(
            "credit_workflow_job_requested company_name=%s",
            body.company_name,
        )
        response_model = submit_workflow_job(
            body.company_name,
            request_id=request_id,
        )
        workflow_job_runner.notify_job_submitted()
        logger.info(
            "credit_workflow_job_queued job_id=%s company_name=%s",
            response_model.job_id,
            response_model.company_name,
        )
        return response_model
    except ValueError as exc:
        logger.info(
            "credit_workflow_job_invalid_input company_name=%s error=%s",
            body.company_name,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=build_workflow_error_response(
                code="INVALID_INPUT",
                message="입력값이 올바르지 않습니다.",
                detail={"company_name": body.company_name},
                request_id=request_id,
            ).model_dump(mode="json"),
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "credit_workflow_job_submit_failed company_name=%s",
            body.company_name,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_workflow_error_response(
                code="JOB_SUBMIT_FAILED",
                message="워크플로우 job 등록 중 오류가 발생했습니다.",
                detail={"company_name": body.company_name},
                request_id=request_id,
            ).model_dump(mode="json"),
        )


@router.get(
    "/jobs/{job_id}",
    response_model=WorkflowJobStatusResponse,
    responses=WORKFLOW_ERROR_RESPONSES,
)
async def get_credit_assessment_job_status(
    job_id: str,
) -> WorkflowJobStatusResponse | JSONResponse:
    request_id = get_request_id()
    try:
        job_status = get_workflow_job_status(job_id)
        if job_status is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=build_workflow_error_response(
                    code="JOB_NOT_FOUND",
                    message="해당 워크플로우 job을 찾을 수 없습니다.",
                    detail={"job_id": job_id},
                    request_id=request_id,
                ).model_dump(mode="json"),
            )
        return job_status
    except Exception:  # noqa: BLE001
        logger.exception("credit_workflow_job_status_failed job_id=%s", job_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_workflow_error_response(
                code="JOB_STATUS_FAILED",
                message="워크플로우 job 상태 조회 중 오류가 발생했습니다.",
                detail={"job_id": job_id},
                request_id=request_id,
            ).model_dump(mode="json"),
        )


@router.get(
    "/jobs/{job_id}/stream",
    response_model=None,
    responses=WORKFLOW_ERROR_RESPONSES,
)
async def stream_credit_assessment_job_status(
    job_id: str,
) -> StreamingResponse | JSONResponse:
    request_id = get_request_id()
    try:
        job_status = get_workflow_job_status(job_id)
        if job_status is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=build_workflow_error_response(
                    code="JOB_NOT_FOUND",
                    message="해당 워크플로우 job을 찾을 수 없습니다.",
                    detail={"job_id": job_id},
                    request_id=request_id,
                ).model_dump(mode="json"),
            )
        return StreamingResponse(
            _stream_workflow_job_events(job_status),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("credit_workflow_job_stream_failed job_id=%s", job_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_workflow_error_response(
                code="JOB_STREAM_FAILED",
                message="워크플로우 job 스트림 생성 중 오류가 발생했습니다.",
                detail={"job_id": job_id},
                request_id=request_id,
            ).model_dump(mode="json"),
        )


@router.get(
    "/jobs/{job_id}/result",
    response_model=WorkflowResponse,
    responses=WORKFLOW_ERROR_RESPONSES,
)
async def get_credit_assessment_job_result(
    job_id: str,
) -> WorkflowResponse | JSONResponse:
    request_id = get_request_id()
    try:
        job_status = get_workflow_job_status(job_id)
        if job_status is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=build_workflow_error_response(
                    code="JOB_NOT_FOUND",
                    message="해당 워크플로우 job을 찾을 수 없습니다.",
                    detail={"job_id": job_id},
                    request_id=request_id,
                ).model_dump(mode="json"),
            )

        if job_status.status != JOB_STATUS_SUCCEEDED:
            error_code = "JOB_NOT_COMPLETED"
            message = "워크플로우 job이 아직 완료되지 않았습니다."
            if job_status.status == JOB_STATUS_FAILED:
                error_code = "JOB_FAILED"
                message = "워크플로우 job이 실패했습니다."

            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=build_workflow_error_response(
                    code=error_code,
                    message=message,
                    detail={"job_id": job_id, "status": job_status.status},
                    request_id=request_id,
                ).model_dump(mode="json"),
            )

        workflow_result = get_workflow_job_result(job_id)
        if workflow_result is None:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=build_workflow_error_response(
                    code="JOB_RESULT_MISSING",
                    message="완료된 job 결과를 찾을 수 없습니다.",
                    detail={"job_id": job_id, "status": job_status.status},
                    request_id=request_id,
                ).model_dump(mode="json"),
            )
        return workflow_result
    except Exception:  # noqa: BLE001
        logger.exception("credit_workflow_job_result_failed job_id=%s", job_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_workflow_error_response(
                code="JOB_RESULT_FAILED",
                message="워크플로우 job 결과 조회 중 오류가 발생했습니다.",
                detail={"job_id": job_id},
                request_id=request_id,
            ).model_dump(mode="json"),
        )


async def _stream_workflow_job_events(
    initial_status: WorkflowJobStatusResponse,
) -> AsyncIterator[str]:
    last_signature: str | None = None
    job_status = initial_status
    while True:
        event_name = _workflow_job_sse_event_name(job_status)
        payload = _workflow_job_sse_payload(job_status)
        signature = json.dumps(
            {"event": event_name, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
        )
        if signature != last_signature:
            yield _format_sse_event(event_name, payload)
            last_signature = signature
        if job_status.status in {JOB_STATUS_SUCCEEDED, JOB_STATUS_FAILED}:
            return
        await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)
        refreshed_status = await asyncio.to_thread(
            get_workflow_job_status,
            job_status.job_id,
        )
        if refreshed_status is None:
            yield _format_sse_event(
                "error",
                {
                    "job_id": job_status.job_id,
                    "status": "failed",
                    "error_code": "JOB_NOT_FOUND",
                    "message": "해당 워크플로우 job을 찾을 수 없습니다.",
                },
            )
            return
        job_status = refreshed_status


def _workflow_job_sse_event_name(job_status: WorkflowJobStatusResponse) -> str:
    if job_status.status == JOB_STATUS_SUCCEEDED:
        return "complete"
    if job_status.status == JOB_STATUS_FAILED:
        return "error"
    if job_status.status == "running" and job_status.step_summary is not None:
        return "progress"
    return job_status.status


def _workflow_job_sse_payload(
    job_status: WorkflowJobStatusResponse,
) -> dict[str, Any]:
    return job_status.model_dump(mode="json", exclude_none=True)


def _format_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_name}\ndata: {data}\n\n"


async def _execute_credit_workflow(
    body: CreditAssessmentRequest,
) -> WorkflowResponse | JSONResponse:
    request_id = get_request_id()
    try:
        logger.info(
            "credit_workflow_requested company_name=%s",
            body.company_name,
        )
        result = await run_credit_workflow(
            body.company_name,
            extra_payload={"request_id": request_id},
        )
        response_model = build_workflow_response(
            result,
            request_id=request_id,
            company_name=body.company_name.strip(),
        )
        logger.info(
            (
                "credit_workflow_completed company_name=%s status=%s step_count=%s"
            ),
            body.company_name,
            response_model.status,
            len(response_model.steps),
        )
        return response_model
    except ValueError as exc:
        logger.info(
            "credit_workflow_invalid_input company_name=%s error=%s",
            body.company_name,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=build_workflow_error_response(
                code="INVALID_INPUT",
                message="입력값이 올바르지 않습니다.",
                detail={"company_name": body.company_name},
                request_id=request_id,
            ).model_dump(mode="json"),
        )
    except Exception:  # noqa: BLE001 - API 계층에서 오케스트레이터 오류 매핑
        logger.exception(
            "credit_workflow_execution_failed company_name=%s",
            body.company_name,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_workflow_error_response(
                code="AGENT_EXECUTION_FAILED",
                message="오케스트레이터 실행 중 오류가 발생했습니다.",
                detail={"company_name": body.company_name},
                request_id=request_id,
            ).model_dump(mode="json"),
        )
