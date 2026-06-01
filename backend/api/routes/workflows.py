import logging
from typing import Any
from uuid import uuid4

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
    request_id = f"req-{uuid4().hex[:12]}"
    try:
        logger.info(
            "credit_workflow_requested request_id=%s company_name=%s",
            request_id,
            body.company_name,
        )
        result = await run_credit_workflow(
            body.company_name,
            extra_payload={"request_id": request_id},
        )
        result.setdefault("request_id", request_id)
        logger.info(
            (
                "credit_workflow_completed request_id=%s company_name=%s "
                "status=%s step_count=%s"
            ),
            request_id,
            body.company_name,
            result.get("status"),
            len(result.get("steps", [])),
        )
        return result
    except ValueError as exc:
        logger.info(
            "credit_workflow_invalid_input request_id=%s company_name=%s error=%s",
            request_id,
            body.company_name,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_INPUT",
                "message": "입력값이 올바르지 않습니다.",
                "detail": {"company_name": body.company_name},
                "request_id": request_id,
            },
        ) from exc
    except Exception as exc:  # noqa: BLE001 - API 계층에서 오케스트레이터 오류 매핑
        logger.exception(
            "credit_workflow_execution_failed request_id=%s company_name=%s",
            request_id,
            body.company_name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "AGENT_EXECUTION_FAILED",
                "message": "오케스트레이터 실행 중 오류가 발생했습니다.",
                "detail": {"company_name": body.company_name},
                "request_id": request_id,
            },
        ) from exc
