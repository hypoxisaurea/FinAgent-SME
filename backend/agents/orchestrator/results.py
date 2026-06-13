from __future__ import annotations

from typing import Any

from backend.agents.orchestrator.state import WorkflowState
from backend.schemas.workflow import (
    WorkflowResponse,
    build_workflow_response,
    derive_status_from_steps,
    summarize_workflow_steps,
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

    return build_workflow_response(
        {
        "status": derive_status_from_steps(steps),
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
