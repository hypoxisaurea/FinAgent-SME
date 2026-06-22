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
VALIDATION_FAILED_CODE = "VALIDATION_FAILED"
VALIDATION_FAILED_MESSAGE = "최종 결과 검증에 실패하여 심사 결과가 차단되었습니다."
BLOCKED_RESULT_KEYS = frozenset(
    {
        "decision",
        "credit_grade",
        "credit_score",
        "decision_confidence",
        "decision_reasons",
        "recommended_limit",
        "limit_range",
        "limit_basis",
        "explanation",
        "grade_detail",
        "processed_at",
        "report",
    }
)


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

    status_steps = _effective_steps_for_status(context, steps)
    status = derive_status_from_steps(status_steps)
    validation_blocked = context.get("validation_gate_status") == "blocked"
    if validation_blocked:
        status = "failed"
        validation_result = context["validation_result"]
        logger.warning(
            (
                "workflow_validation_blocked company_name=%s "
                "pass_rate=%s failed_checks=%s"
            ),
            context.get("company_name"),
            validation_result.get("pass_rate"),
            validation_result.get("failed_checks", []),
        )
        context = {
            key: value
            for key, value in context.items()
            if key not in BLOCKED_RESULT_KEYS
        }

    return build_workflow_response(
        {
            "status": status,
            "code": VALIDATION_FAILED_CODE if validation_blocked else None,
            "message": VALIDATION_FAILED_MESSAGE if validation_blocked else None,
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


def _effective_steps_for_status(
    context: dict[str, Any],
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if context.get("validation_gate_status") != "passed":
        return steps
    last_validation_index = max(
        (
            index
            for index, step in enumerate(steps)
            if step.get("agent_name") == "validation"
        ),
        default=-1,
    )
    return [
        step
        for index, step in enumerate(steps)
        if step.get("agent_name") != "validation" or index == last_validation_index
    ]
