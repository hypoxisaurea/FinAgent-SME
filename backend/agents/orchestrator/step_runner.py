from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.agents.base import Agent
from backend.agents.contracts import (
    build_agent_failure_output,
    build_agent_output,
    classify_agent_error,
    extract_agent_business_output,
    extract_agent_execution,
    is_agent_step_ok,
    resolve_agent_retry_attempts,
    resolve_agent_retry_backoff_seconds,
    resolve_agent_timeout_seconds,
    should_retry_agent_error,
)

logger = logging.getLogger("backend.agents.orchestrator.orchestrator")


@dataclass(slots=True)
class StepResult:
    """오케스트레이션 단일 단계 실행 결과."""

    agent_name: str
    ok: bool
    status: str
    error_code: str
    fallback_used: bool
    latency_ms: int
    output: dict[str, Any]
    error: str | None = None


async def run_agent_step(agent: Agent, context: dict[str, Any]) -> StepResult:
    """Agent 한 단계를 공통 timeout/retry 정책으로 실행한다."""
    agent_name = getattr(agent, "name", agent.__class__.__name__)
    timeout_seconds = resolve_agent_timeout_seconds(context, agent_name)
    retry_attempts = resolve_agent_retry_attempts(context, agent_name)
    retry_backoff_seconds = resolve_agent_retry_backoff_seconds(context, agent_name)
    logger.info(
        (
            "workflow_agent_execution_config company_name=%s agent_name=%s "
            "timeout_seconds=%s retry_attempts=%s "
            "retry_backoff_seconds=%s"
        ),
        context.get("company_name"),
        agent_name,
        timeout_seconds,
        retry_attempts,
        retry_backoff_seconds,
    )
    attempt = 0

    while attempt < retry_attempts:
        attempt += 1
        started_at = asyncio.get_running_loop().time()
        try:
            raw_output = await asyncio.wait_for(agent.run(context), timeout_seconds)
            if not isinstance(raw_output, dict):
                raise TypeError(
                    f"{agent_name}.run() 반환값은 dict여야 합니다. "
                    f"실제 타입: {type(raw_output).__name__}"
                )

            contract_output = build_agent_output(
                raw_output,
                latency_ms=int((asyncio.get_running_loop().time() - started_at) * 1000),
            )
            execution = extract_agent_execution(contract_output)
            return StepResult(
                agent_name=agent_name,
                ok=is_agent_step_ok(execution["status"]),
                status=execution["status"],
                error_code=execution["error_code"],
                fallback_used=execution["fallback_used"],
                latency_ms=execution["latency_ms"],
                output=extract_agent_business_output(contract_output),
                error=(
                    None
                    if is_agent_step_ok(execution["status"])
                    else execution["error_code"]
                ),
            )
        except Exception as exc:  # noqa: BLE001
            error_code = classify_agent_error(exc)
            if attempt < retry_attempts and should_retry_agent_error(exc):
                logger.warning(
                    (
                        "workflow_agent_retry company_name=%s agent_name=%s "
                        "attempt=%s max_attempts=%s "
                        "error_code=%s error=%s"
                    ),
                    context.get("company_name"),
                    agent_name,
                    attempt,
                    retry_attempts,
                    error_code,
                    exc,
                )
                await asyncio.sleep(retry_backoff_seconds * attempt)
                continue

            failure_output = build_agent_failure_output(
                error_code=error_code,
                latency_ms=int((asyncio.get_running_loop().time() - started_at) * 1000),
            )
            execution = extract_agent_execution(failure_output)
            return StepResult(
                agent_name=agent_name,
                ok=False,
                status=execution["status"],
                error_code=execution["error_code"],
                fallback_used=execution["fallback_used"],
                latency_ms=execution["latency_ms"],
                output=extract_agent_business_output(failure_output),
                error=str(exc),
            )

    failure_output = build_agent_failure_output(
        error_code="AGENT_EXECUTION_FAILED",
        latency_ms=0,
    )
    execution = extract_agent_execution(failure_output)
    return StepResult(
        agent_name=agent_name,
        ok=False,
        status=execution["status"],
        error_code=execution["error_code"],
        fallback_used=execution["fallback_used"],
        latency_ms=execution["latency_ms"],
        output={},
        error="알 수 없는 에이전트 실행 실패",
    )
