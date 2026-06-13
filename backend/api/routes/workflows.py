import logging

from backend.agents.orchestrator import run_credit_workflow
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
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])
logger = logging.getLogger(__name__)


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
