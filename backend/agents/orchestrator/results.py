from __future__ import annotations

from typing import Any

from backend.agents.orchestrator.state import WorkflowState


def build_result(state: WorkflowState) -> dict[str, Any]:
    """그래프 최종 상태를 API 응답용 결과로 정규화한다."""
    context = dict(state.get("context", {}))
    steps = list(state.get("steps", []))

    if context.get("company_found") is False:
        return {
            "status": "not_target",
            "code": context.get("workflow_code", "COMPANY_NOT_FOUND"),
            "message": context.get(
                "workflow_message",
                "대상 기업이 아닙니다.",
            ),
            "context": context,
            "steps": steps,
        }

    return {
        "status": derive_status(steps),
        "context": context,
        "steps": steps,
    }


def derive_status(steps: list[dict[str, Any]]) -> str:
    """step 결과 목록에서 전체 워크플로우 상태를 계산한다."""
    if not steps:
        return "not_started"
    ok_count = sum(1 for step in steps if step["ok"])
    if ok_count == len(steps):
        return "success"
    if ok_count == 0:
        return "failed"
    return "partial"


def summarize_steps(steps: list[dict[str, Any]]) -> dict[str, int]:
    """step 목록을 상태별 카운트로 요약한다."""
    success_steps = sum(1 for step in steps if step.get("status") == "success")
    partial_steps = sum(1 for step in steps if step.get("status") == "partial")
    failed_steps = sum(1 for step in steps if step.get("status") == "failed")
    fallback_steps = sum(1 for step in steps if step.get("fallback_used") is True)
    return {
        "success": success_steps,
        "partial": partial_steps,
        "failed": failed_steps,
        "fallback": fallback_steps,
    }

