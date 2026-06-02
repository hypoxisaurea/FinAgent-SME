import logging
from typing import Any

from backend.agents.orchestrator import run_credit_workflow
from backend.common.logging import get_request_id
from backend.schemas.credit import CreditAssessmentRequest
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])
logger = logging.getLogger(__name__)


@router.post("/credit-assessment")
async def credit_assessment(body: CreditAssessmentRequest) -> dict[str, Any]:
    return await _execute_credit_workflow(body)


@router.post("/orchestrator")
async def credit_assessment_orchestrator(
    body: CreditAssessmentRequest,
) -> dict[str, Any]:
    return await _execute_credit_workflow(body)


async def _execute_credit_workflow(body: CreditAssessmentRequest) -> dict[str, Any]:
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
        result.setdefault("request_id", request_id)
        logger.info(
            (
                "credit_workflow_completed company_name=%s status=%s step_count=%s"
            ),
            body.company_name,
            result.get("status"),
            len(result.get("steps", [])),
        )
        return result
    except ValueError as exc:
        logger.info(
            "credit_workflow_invalid_input company_name=%s error=%s",
            body.company_name,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "code": "INVALID_INPUT",
                "message": "입력값이 올바르지 않습니다.",
                "detail": {"company_name": body.company_name},
                "request_id": request_id,
            },
        )
    except Exception:  # noqa: BLE001 - API 계층에서 오케스트레이터 오류 매핑
        logger.exception(
            "credit_workflow_execution_failed company_name=%s",
            body.company_name,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "AGENT_EXECUTION_FAILED",
                "message": "오케스트레이터 실행 중 오류가 발생했습니다.",
                "detail": {"company_name": body.company_name},
                "request_id": request_id,
            },
        )
