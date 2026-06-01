# Agent Execution Contract

## 목적

모든 Agent 실행 결과를 동일한 형식으로 표준화하여, 오케스트레이터의 부분 실패 처리, 운영 추적, 평가 파이프라인 연계를 단순화한다.

## 공통 출력 필드

모든 `Agent.run(payload)` 반환값은 아래 필드를 포함해야 한다.

```json
{
  "status": "success",
  "error_code": "OK",
  "fallback_used": false,
  "latency_ms": 123
}
```

- `status`
  - `success`: 정상 완료
  - `partial`: 부분 성공, 축약 결과 또는 일부 핸들러 실패 포함
  - `failed`: 결과를 downstream에 안전하게 전달할 수 없음
  - `skipped`: 조건 미충족으로 의도적으로 생략
- `error_code`
  - 성공 시 기본값은 `OK`
  - 실패/부분 성공 시 안정적인 `UPPER_SNAKE_CASE` 코드 사용
- `fallback_used`
  - 규칙 기반 대체 응답, 축약 결과, 부분 집계 등 fallback 경로 사용 여부
- `latency_ms`
  - Agent 단위 실행 시간(밀리초)

## 권장 에러 코드

- `OK`
- `INVALID_INPUT`
- `INVALID_OUTPUT`
- `AGENT_TIMEOUT`
- `UPSTREAM_UNAVAILABLE`
- `RESOURCE_NOT_FOUND`
- `AGENT_EXECUTION_FAILED`

도메인별 세부 코드는 허용하지만, 위 공통 코드와 의미가 충돌하면 안 된다.

## 오케스트레이터 규칙

- 오케스트레이터는 Agent 출력에서 공통 메타데이터를 분리해 `steps`에 기록한다.
- 비즈니스 데이터만 공유 `context`에 병합한다.
- `status=failed`는 downstream 중단 후보로 간주한다.
- `status=partial`은 downstream 전달은 허용하되, 최종 워크플로우 상태 계산 시 부분 성공의 근거로 남긴다.

## Timeout / Retry / Fallback 정책

### Timeout

- 기본 타임아웃: `45초`
- payload override:
  - `agent_timeout_seconds`
  - `agent_timeouts.<agent_name>`

### Retry

- 기본 재시도 횟수: `1회`(즉, 재실행 없음)
- payload override:
  - `default_agent_retry_attempts`
  - `agent_retry_attempts.<agent_name>`
- 재시도 대상:
  - 타임아웃
  - 일시적 네트워크/OS 계층 오류
- 재시도 비대상:
  - `ValueError`
  - `TypeError`
  - `FileNotFoundError`

### Fallback

- fallback은 예외를 숨기는 수단이 아니라, 품질 저하를 명시적으로 드러내는 수단이다.
- fallback 사용 시:
  - `fallback_used=true`
  - `status=partial` 또는 `status=success`
  - `error_code`를 `OK` 외 코드로 명시하는 것을 권장

## 구현 메모

- 공통 헬퍼는 `backend/agents/contracts.py`를 사용한다.
- Agent 내부 tool 호출은 `backend/agents/tool_runtime.py`로 감싸는 것을 권장한다.
- 개별 Agent는 가능하면 직접 공통 필드를 반환하고, 오케스트레이터는 누락 시 동일 계약으로 보정한다.
- 외부 API/Tool 실패 시 Agent 전체를 즉시 실패시키기보다, 가능한 범위의 fallback 결과와 `tool_errors`를 함께 남긴다.
- Agent별로 `*_tool_runs`, `*_tool_errors` 형태의 namespaced 실행 흔적을 보존할 수 있다.
- 테스트는 최소 한 건 이상 `status`, `error_code`, `fallback_used`, `latency_ms` 존재를 검증해야 한다.
