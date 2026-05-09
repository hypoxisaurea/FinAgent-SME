from typing import Any

from fastapi import APIRouter

from agents.orchestrator import run_credit_workflow
from schemas.credit import CreditAssessmentRequest

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


@router.post("/credit-assessment")
async def credit_assessment(body: CreditAssessmentRequest) -> dict[str, Any]:
    return await run_credit_workflow(body.company_name)
