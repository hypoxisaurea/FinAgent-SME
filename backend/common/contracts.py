from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

AGENT_SUCCESS_STATUS = "success"
AGENT_PARTIAL_STATUS = "partial"
AGENT_FAILED_STATUS = "failed"
AGENT_SKIPPED_STATUS = "skipped"
DEFAULT_AGENT_TIMEOUT_SECONDS = 45.0
DEFAULT_AGENT_RETRY_ATTEMPTS = 1
DEFAULT_AGENT_RETRY_BACKOFF_SECONDS = 0.5
AGENT_METADATA_KEYS = frozenset(
    {
        "status",
        "error_code",
        "fallback_used",
        "latency_ms",
        "agent_execution",
    }
)


def elapsed_ms(started_at: float) -> int:
    """성능 측정용 monotonic 시작 시각을 밀리초 단위로 변환한다."""
    return max(int((perf_counter() - started_at) * 1000), 0)


def resolve_agent_timeout_seconds(payload: dict[str, Any], agent_name: str) -> float:
    """에이전트 타임아웃 설정을 해석한다."""
    agent_timeouts = payload.get("agent_timeouts")
    if isinstance(agent_timeouts, dict) and agent_name in agent_timeouts:
        return float(agent_timeouts[agent_name])
    return float(payload.get("agent_timeout_seconds", DEFAULT_AGENT_TIMEOUT_SECONDS))


def resolve_agent_retry_attempts(payload: dict[str, Any], agent_name: str) -> int:
    """에이전트 재시도 횟수 설정을 해석한다."""
    agent_retry_attempts = payload.get("agent_retry_attempts")
    if isinstance(agent_retry_attempts, dict) and agent_name in agent_retry_attempts:
        return max(int(agent_retry_attempts[agent_name]), 1)
    return max(
        int(
            payload.get(
                "default_agent_retry_attempts",
                DEFAULT_AGENT_RETRY_ATTEMPTS,
            )
        ),
        1,
    )


def resolve_agent_retry_backoff_seconds(
    payload: dict[str, Any],
    agent_name: str,
) -> float:
    """에이전트 재시도 백오프 설정을 해석한다."""
    retry_backoffs = payload.get("agent_retry_backoff_seconds")
    if isinstance(retry_backoffs, dict) and agent_name in retry_backoffs:
        return max(float(retry_backoffs[agent_name]), 0.0)
    return max(
        float(
            payload.get(
                "default_agent_retry_backoff_seconds",
                DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
            )
        ),
        0.0,
    )


def should_retry_agent_error(exc: Exception) -> bool:
    """일시적 오류만 공통 재시도 대상으로 본다."""
    if isinstance(exc, (ValueError, TypeError, FileNotFoundError)):
        return False
    return isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError))


def classify_agent_error(exc: Exception) -> str:
    """예외 타입을 공통 에러 코드로 정규화한다."""
    if isinstance(exc, asyncio.TimeoutError):
        return "AGENT_TIMEOUT"
    if isinstance(exc, ValueError):
        return "INVALID_INPUT"
    if isinstance(exc, TypeError):
        return "INVALID_OUTPUT"
    if isinstance(exc, FileNotFoundError):
        return "RESOURCE_NOT_FOUND"
    if isinstance(exc, (ConnectionError, OSError)):
        return "UPSTREAM_UNAVAILABLE"
    return "AGENT_EXECUTION_FAILED"


def build_agent_output(
    payload: dict[str, Any] | None,
    *,
    status: str = AGENT_SUCCESS_STATUS,
    error_code: str = "OK",
    fallback_used: bool = False,
    latency_ms: int = 0,
) -> dict[str, Any]:
    """에이전트 공통 실행 메타데이터를 payload에 합친다."""
    output = dict(payload or {})
    normalized_status = str(output.get("status", status) or AGENT_SUCCESS_STATUS)
    normalized_error_code = str(output.get("error_code", error_code) or "OK")
    normalized_fallback_used = bool(output.get("fallback_used", fallback_used))
    normalized_latency_ms = int(output.get("latency_ms", latency_ms) or 0)

    output.update(
        {
            "status": normalized_status,
            "error_code": normalized_error_code,
            "fallback_used": normalized_fallback_used,
            "latency_ms": normalized_latency_ms,
            "agent_execution": {
                "status": normalized_status,
                "error_code": normalized_error_code,
                "fallback_used": normalized_fallback_used,
                "latency_ms": normalized_latency_ms,
            },
        }
    )
    return output


def build_agent_failure_output(
    *,
    error_code: str,
    latency_ms: int,
    fallback_used: bool = False,
) -> dict[str, Any]:
    """실패한 에이전트 출력의 기본 메타데이터를 생성한다."""
    return build_agent_output(
        {},
        status=AGENT_FAILED_STATUS,
        error_code=error_code,
        fallback_used=fallback_used,
        latency_ms=latency_ms,
    )


def extract_agent_business_output(payload: dict[str, Any]) -> dict[str, Any]:
    """공통 메타데이터를 제외한 순수 비즈니스 출력만 반환한다."""
    return {
        key: value
        for key, value in payload.items()
        if key not in AGENT_METADATA_KEYS
    }


def extract_agent_execution(payload: dict[str, Any]) -> dict[str, Any]:
    """에이전트 실행 메타데이터를 추출한다."""
    agent_execution = payload.get("agent_execution")
    if isinstance(agent_execution, dict):
        return {
            "status": str(
                agent_execution.get(
                    "status",
                    payload.get("status", AGENT_SUCCESS_STATUS),
                )
            ),
            "error_code": str(
                agent_execution.get("error_code", payload.get("error_code", "OK"))
            ),
            "fallback_used": bool(
                agent_execution.get(
                    "fallback_used",
                    payload.get("fallback_used", False),
                )
            ),
            "latency_ms": int(
                agent_execution.get("latency_ms", payload.get("latency_ms", 0))
                or 0
            ),
        }

    return {
        "status": str(payload.get("status", AGENT_SUCCESS_STATUS)),
        "error_code": str(payload.get("error_code", "OK")),
        "fallback_used": bool(payload.get("fallback_used", False)),
        "latency_ms": int(payload.get("latency_ms", 0) or 0),
    }


def is_agent_step_ok(status: str) -> bool:
    """실패 상태가 아닌 경우 downstream 전달이 가능하다고 본다."""
    return status != AGENT_FAILED_STATUS
