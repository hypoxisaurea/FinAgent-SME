import logging

from backend.agents.orchestrator import run_credit_workflow
from backend.common.logging import get_request_id
from backend.schemas.credit import CreditAssessmentRequest
from backend.schemas.workflow import (
    WorkflowErrorResponse,
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
