from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from backend.common.agent import Agent
from backend.common.contracts import (
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
from pydantic import BaseModel, ValidationError

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
            validated_input = _validate_agent_input(agent, context)
            raw_output = await asyncio.wait_for(agent.run(validated_input), timeout_seconds)
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
            business_output = extract_agent_business_output(contract_output)
            if is_agent_step_ok(execution["status"]):
                business_output = _validate_agent_output(agent, business_output)
            return StepResult(
                agent_name=agent_name,
                ok=is_agent_step_ok(execution["status"]),
                status=execution["status"],
                error_code=execution["error_code"],
                fallback_used=execution["fallback_used"],
                latency_ms=execution["latency_ms"],
                output=business_output,
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


def _validate_agent_input(agent: Agent, payload: dict[str, Any]) -> dict[str, Any]:
    model_type = _get_agent_model(agent, "input_model")
    if model_type is None:
        return payload

    try:
        validated_model = model_type.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(_format_contract_error(agent, "input", exc)) from exc

    return validated_model.model_dump(mode="python", exclude_none=True)


def _validate_agent_output(agent: Agent, payload: dict[str, Any]) -> dict[str, Any]:
    model_type = _get_agent_model(agent, "output_model")
    if model_type is None:
        return payload

    try:
        validated_model = model_type.model_validate(payload)
    except ValidationError as exc:
        raise TypeError(_format_contract_error(agent, "output", exc)) from exc

    return validated_model.model_dump(mode="python", exclude_none=True)


def _get_agent_model(
    agent: Agent,
    attribute_name: str,
) -> type[BaseModel] | None:
    model_type = getattr(agent, attribute_name, None)
    if model_type is None:
        return None
    if not isinstance(model_type, type) or not issubclass(model_type, BaseModel):
        raise TypeError(
            f"{getattr(agent, 'name', agent.__class__.__name__)}.{attribute_name} "
            "must be a Pydantic BaseModel subclass."
        )
    return model_type


def _format_contract_error(
    agent: Agent,
    contract_type: str,
    exc: ValidationError,
) -> str:
    details = ", ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
    agent_name = getattr(agent, "name", agent.__class__.__name__)
    return f"{agent_name} {contract_type} contract validation failed ({details})"
