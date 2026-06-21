from __future__ import annotations

import logging
from typing import Any

from backend.agents.orchestrator.state import WorkflowState
from backend.schemas.workflow import (
    WorkflowResponse,
    build_workflow_response,
    derive_status_from_steps,
    summarize_workflow_steps,
)

logger = logging.getLogger(__name__)
VALIDATION_WARNING_CODE = "VALIDATION_WARNING"
VALIDATION_WARNING_MESSAGE = "최종 결과 검증에서 경고가 발생했습니다."


def build_result(state: WorkflowState) -> WorkflowResponse:
    """그래프 최종 상태를 API 응답용 결과로 정규화한다."""
    context = dict(state.get("context", {}))
    steps = list(state.get("steps", []))

    if context.get("company_found") is False:
        return build_workflow_response(
            {
                "status": "not_target",
                "code": context.get("workflow_code", "COMPANY_NOT_FOUND"),
                "message": context.get(
                    "workflow_message",
                    "대상 기업이 아닙니다.",
                ),
                "context": context,
                "steps": steps,
            }
        )

    status = derive_status_from_steps(steps)
    validation_failed = _has_failed_validation(context)
    if validation_failed:
        status = "partial"
        validation_result = context["validation_result"]
        logger.warning(
            (
                "workflow_validation_warning company_name=%s "
                "pass_rate=%s failed_checks=%s"
            ),
            context.get("company_name"),
            validation_result.get("pass_rate"),
            validation_result.get("failed_checks", []),
        )

    return build_workflow_response(
        {
            "status": status,
            "code": VALIDATION_WARNING_CODE if validation_failed else None,
            "message": VALIDATION_WARNING_MESSAGE if validation_failed else None,
            "context": context,
            "steps": steps,
        }
    )


def derive_status(steps: list[dict[str, Any]]) -> str:
    """step 결과 목록에서 전체 워크플로우 상태를 계산한다."""
    return derive_status_from_steps(steps)


def summarize_steps(steps: list[dict[str, Any]]) -> dict[str, int]:
    """step 목록을 상태별 카운트로 요약한다."""
    return summarize_workflow_steps(steps)


def _has_failed_validation(context: dict[str, Any]) -> bool:
    validation_result = context.get("validation_result")
    return (
        isinstance(validation_result, dict)
        and validation_result.get("validation_passed") is False
    )
