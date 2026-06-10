# Agent Execution Contract

## 목적

모든 agent 실행 결과를 표준화해 오케스트레이터, 로깅, 테스트, Langfuse 추적을 단순화한다.

## 공통 출력 필드

모든 `Agent.run(payload)` 반환값은 아래 메타데이터를 포함하거나, 최소한 `build_agent_output()`으로 보정 가능해야 한다.

```json
{
  "status": "success",
  "error_code": "OK",
  "fallback_used": false,
  "latency_ms": 123,
  "agent_execution": {
    "status": "success",
    "error_code": "OK",
    "fallback_used": false,
    "latency_ms": 123
  }
}
```

## `status` 의미

- `success`: 정상 완료
- `partial`: fallback 또는 일부 내부 처리 degraded
- `failed`: downstream에 안전하게 전달할 수 없는 실패
- `skipped`: 조건 미충족으로 의도적으로 생략

## `error_code` 규칙

- 성공 시 기본값은 `OK`
- 실패/부분 성공 시 안정적인 `UPPER_SNAKE_CASE`

예시:

- `OK`
- `INVALID_INPUT`
- `INVALID_OUTPUT`
- `AGENT_TIMEOUT`
- `UPSTREAM_UNAVAILABLE`
- `RESOURCE_NOT_FOUND`
- `AGENT_EXECUTION_FAILED`

## 오케스트레이터 처리 규칙

- 오케스트레이터는 agent 출력에서 메타데이터를 추출해 `steps`에 남긴다.
- 비즈니스 데이터만 `context`에 병합한다.
- `status=failed`는 `ok=False`로 처리된다.
- `status=success`, `partial`, `skipped`는 현재 `ok=True`로 처리된다.

즉, 전체 workflow 상태는 agent의 `status` 문자열이 아니라 `step.ok` 집계에 의해 계산된다.

## Timeout / Retry 정책

- 기본 timeout: `45초`
- payload override:
  - `agent_timeout_seconds`
  - `agent_timeouts.<agent_name>`

- 기본 retry attempts: `1`
- payload override:
  - `default_agent_retry_attempts`
  - `agent_retry_attempts.<agent_name>`

- 기본 backoff: `0.5초`
- payload override:
  - `default_agent_retry_backoff_seconds`
  - `agent_retry_backoff_seconds.<agent_name>`

## Retry 대상 예외

- `asyncio.TimeoutError`
- `ConnectionError`
- `OSError`

## Retry 비대상 예외

- `ValueError`
- `TypeError`
- `FileNotFoundError`

## 구현 메모

- 공통 helper는 `backend/common/contracts.py`
- orchestrator step 실행은 `backend/agents/orchestrator/step_runner.py`
- tool fallback helper는 `backend/common/tool_runtime.py`
- 테스트는 최소 한 번 이상 `steps` 메타데이터 존재를 검증해야 한다
