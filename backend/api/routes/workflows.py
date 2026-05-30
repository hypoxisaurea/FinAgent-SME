import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from agents.orchestrator import run_credit_workflow
from schemas.credit import CreditAssessmentRequest

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
    try:
        logger.info("credit_workflow_requested company_name=%s", body.company_name)
        result = await run_credit_workflow(body.company_name)
        logger.info(
            "credit_workflow_completed company_name=%s status=%s",
            body.company_name,
            result.get("status"),
        )
        return result
    except ValueError as exc:
        logger.info(
            "credit_workflow_invalid_input company_name=%s error=%s",
            body.company_name,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "message": "입력값이 올바르지 않습니다.",
                "detail": {"company_name": body.company_name},
            },
        ) from exc
    except Exception as exc:  # noqa: BLE001 - API 계층에서 오케스트레이터 오류 매핑
        logger.exception(
            "credit_workflow_execution_failed company_name=%s",
            body.company_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "AGENT_EXECUTION_FAILED",
                "message": "오케스트레이터 실행 중 오류가 발생했습니다.",
                "detail": {"company_name": body.company_name},
            },
        ) from exc
