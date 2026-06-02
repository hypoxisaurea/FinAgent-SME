from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_context(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    """LangGraph 상태 병합 시 context dict를 누적한다."""
    merged: dict[str, Any] = dict(left or {})
    merged.update(right or {})
    return merged


class WorkflowState(TypedDict, total=False):
    """LangGraph 오케스트레이션 상태."""

    context: Annotated[dict[str, Any], merge_context]
    steps: Annotated[list[dict[str, Any]], operator.add]

