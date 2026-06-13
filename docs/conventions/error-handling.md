# Error Handling Conventions

## 목적

오류를 예측 가능하게 노출하고, 운영자가 `request_id` 기준으로 추적할 수 있게 한다.

## 계층별 원칙

### Agent 계층

- `Agent.run()`은 가능하면 `build_agent_output()` 형식의 결과를 반환한다.
- 복구 가능한 도구 오류는 fallback으로 축약하고 `fallback_used=true`를 남긴다.
- 복구 불가 예외는 숨기지 말고 오케스트레이터까지 전파한다.

### Orchestrator 계층

- 각 agent 결과는 `steps`에 남긴다.
- 기본 동작은 `fail-fast`다.
- 내부 옵션 `continue_on_error=True`일 때만 후속 단계 지속을 허용한다.
- 공통 실행 메타데이터는 `context`가 아니라 `steps`에 유지한다.

### API 계층

- 입력 검증/정규화 오류: `400`
- 내부 실행 오류: `500`
- 대상 기업 미존재는 예외가 아니라 `200 + status=not_target`

## 현재 표준 에러 응답

```json
{
  "code": "INVALID_INPUT",
  "message": "입력값이 올바르지 않습니다.",
  "detail": {
    "company_name": "   "
  },
  "request_id": "req-1234"
}
```

필드 의미:

- `code`: 안정적인 기계 판독용 코드
- `message`: 사용자/운영자용 요약
- `detail`: 부가 맥락
- `request_id`: 로그/trace 상관관계 ID

## 공통 에러 코드

- `INVALID_INPUT`
- `INVALID_OUTPUT`
- `RESOURCE_NOT_FOUND`
- `UPSTREAM_UNAVAILABLE`
- `AGENT_TIMEOUT`
- `AGENT_EXECUTION_FAILED`

현재 agent/도메인 코드 예시:

- `FINANCIAL_TOOL_FALLBACK`
- `INDUSTRY_TOOL_FALLBACK`
- `RISK_SIGNAL_PARTIAL`
- `DECISION_DEGRADED`
- `REPORT_FALLBACK_USED`
- `VALIDATION_WARNING`

## 로깅 규칙

- `print()` 금지, `logger` 사용
- 요청 시작/종료, agent 시작/종료, retry, fallback, 최종 상태를 기록
- 로그에는 가능한 한 `request_id`, `agent_name`, `error_code`를 포함
- 민감정보는 기록하지 않는다
- 외부 응답에는 stack trace를 노출하지 않는다

## Retry / Timeout

- 기본 timeout: `45초`
- 기본 retry attempts: `1`
  - 총 시도 횟수 기준이므로 기본값은 재실행 없음
- 재시도 대상:
  - `asyncio.TimeoutError`
  - `ConnectionError`
  - `OSError`
- 재시도 비대상:
  - `ValueError`
  - `TypeError`
  - `FileNotFoundError`

## 금지 사항

- `except Exception: pass`
- 서로 다른 실패 원인을 같은 코드로 뭉개기
- 내부 예외 문자열과 stack trace를 API 응답에 그대로 노출하기
