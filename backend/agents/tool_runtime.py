from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Callable

from backend.agents.contracts import (
    AGENT_SKIPPED_STATUS,
    classify_agent_error,
    elapsed_ms,
)


@dataclass(slots=True)
class ToolRunResult:
    """Agent 내부 tool 실행 결과."""

    tool_name: str
    status: str
    error_code: str
    fallback_used: bool
    latency_ms: int
    error: str | None = None


def execute_tool_step(
    *,
    logger: logging.Logger,
    agent_name: str,
    tool_name: str,
    request_id: str | None,
    company_name: str | None,
    runner: Callable[[], Any],
    fallback_factory: Callable[[], Any] | None = None,
    validate_dict: bool = False,
) -> tuple[Any, ToolRunResult]:
    """Agent 내부 tool 호출을 공통 규약으로 실행한다."""
    started_at = perf_counter()
    logger.info(
        "agent_tool_started request_id=%s company_name=%s agent_name=%s tool_name=%s",
        request_id,
        company_name,
        agent_name,
        tool_name,
    )
    try:
        value = runner()
        if validate_dict and not isinstance(value, dict):
            raise TypeError(
                f"{agent_name}.{tool_name} 반환값은 dict여야 합니다. "
                f"실제 타입: {type(value).__name__}"
            )
        tool_run = ToolRunResult(
            tool_name=tool_name,
            status="success",
            error_code="OK",
            fallback_used=False,
            latency_ms=elapsed_ms(started_at),
        )
        logger.info(
            (
                "agent_tool_completed request_id=%s company_name=%s "
                "agent_name=%s tool_name=%s latency_ms=%s"
            ),
            request_id,
            company_name,
            agent_name,
            tool_name,
            tool_run.latency_ms,
        )
        return value, tool_run
    except Exception as exc:  # noqa: BLE001
        error_code = classify_agent_error(exc)
        if fallback_factory is None:
            logger.exception(
                (
                    "agent_tool_failed request_id=%s company_name=%s "
                    "agent_name=%s tool_name=%s error_code=%s"
                ),
                request_id,
                company_name,
                agent_name,
                tool_name,
                error_code,
            )
            raise

        fallback_value = fallback_factory()
        tool_run = ToolRunResult(
            tool_name=tool_name,
            status="partial",
            error_code=error_code,
            fallback_used=True,
            latency_ms=elapsed_ms(started_at),
            error=str(exc),
        )
        logger.warning(
            (
                "agent_tool_fallback request_id=%s company_name=%s "
                "agent_name=%s tool_name=%s error_code=%s latency_ms=%s error=%s"
            ),
            request_id,
            company_name,
            agent_name,
            tool_name,
            error_code,
            tool_run.latency_ms,
            exc,
        )
        return fallback_value, tool_run


def build_skipped_tool_result(
    *,
    tool_name: str,
    reason: str,
) -> ToolRunResult:
    """선행 입력 부족 등으로 생략한 tool 실행 결과를 생성한다."""
    return ToolRunResult(
        tool_name=tool_name,
        status=AGENT_SKIPPED_STATUS,
        error_code=reason,
        fallback_used=False,
        latency_ms=0,
        error=None,
    )


def summarize_tool_runs(
    tool_runs: list[ToolRunResult],
) -> tuple[bool, list[dict[str, Any]]]:
    """tool 실행 결과에서 fallback 여부와 오류 목록을 추출한다."""
    fallback_used = any(tool_run.fallback_used for tool_run in tool_runs)
    tool_errors = [
        {
            "tool_name": tool_run.tool_name,
            "status": tool_run.status,
            "error_code": tool_run.error_code,
            "fallback_used": tool_run.fallback_used,
            "latency_ms": tool_run.latency_ms,
            "error": tool_run.error,
        }
        for tool_run in tool_runs
        if tool_run.status != "success"
    ]
    return fallback_used, tool_errors


def serialize_tool_runs(tool_runs: list[ToolRunResult]) -> list[dict[str, Any]]:
    """tool 실행 결과를 응답 저장용 dict로 직렬화한다."""
    return [asdict(tool_run) for tool_run in tool_runs]
