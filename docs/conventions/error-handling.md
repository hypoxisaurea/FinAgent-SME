# Error Handling Conventions

## 목적

오류를 예측 가능하고 추적 가능하게 처리하여, 심사 결과의 신뢰성과 운영 안정성을 확보한다.

## 계층별 원칙

### 1) Agent 계층

- Agent는 예외 발생 시 원인 식별이 가능한 메시지를 포함해야 한다.
- Agent 내부에서 복구 가능한 오류만 로컬 재시도한다.
- 복구 불가 오류는 감추지 말고 상위(Orchestrator)로 전파한다.
- Agent 출력은 `docs/conventions/agent-execution-contract.md`의 공통 실행 계약을 따른다.
- 최소 공통 필드: `status`, `error_code`, `fallback_used`, `latency_ms`

### 2) Orchestrator 계층

- 모든 단계 실행 결과를 `steps`에 기록한다.
- 기본 정책은 `fail-fast`이며, 설정으로 `continue_on_error`를 허용할 수 있다.
- Agent 오류는 단계 오류로 집계하고 전체 상태(`success/partial/failed`)를 계산한다.
- Agent 메타데이터는 `steps`에 보존하고, 비즈니스 데이터만 공유 `context`에 병합한다.

### 3) API 계층

- 입력 유효성 오류: `4xx`
- 리소스/도메인 규칙 위반: `4xx`
- 내부 처리 실패: `5xx`
- 응답은 표준 에러 포맷을 따른다.

## 표준 에러 응답 포맷

```json
{
  "code": "INTERNAL_ERROR",
  "message": "요청 처리 중 오류가 발생했습니다.",
  "detail": {},
  "request_id": "req-1234"
}
```

- `code`: 기계 판독 가능한 안정 식별자
- `message`: 사용자/운영자 이해 가능한 요약
- `detail`: 디버깅 가능한 부가 정보(민감정보 제외)
- `request_id`: 추적용 상관관계 ID

## 에러 코드 네이밍

- 형식: `UPPER_SNAKE_CASE`
- 예시:
  - `INVALID_INPUT`
  - `WORKFLOW_NOT_CONFIGURED`
  - `AGENT_EXECUTION_FAILED`
  - `INTERNAL_ERROR`

## 로깅 규칙

- `print()` 금지, `logger` 사용
- 개발자 콘솔 추적은 `logger.info()`, `logger.warning()`, `logger.exception()`로 남긴다
- 요청 시작/종료, Agent 시작/완료, retry, fallback, 최종 상태는 콘솔에서 바로 구분 가능해야 한다
- 로그 필수 항목: `request_id`, `agent_name`(해당 시), `error_code`
- 민감정보(개인식별정보, 계좌번호, 토큰, 키) 로그 금지
- stack trace는 내부 로그에만 남기고 외부 응답에는 노출하지 않는다

## 재시도 정책

- 재시도 대상: 일시적 네트워크 오류, 타임아웃
- 재시도 비대상: 입력 오류, 스키마 오류, 비즈니스 규칙 위반
- 재시도 시 지수 백오프를 사용하고 최대 횟수를 제한한다
- 기본값은 `1회`이며, override가 없는 Agent는 자동 재시도를 하지 않는다

## 금지 사항

- 예외를 `except Exception: pass`로 무시 금지
- 사용자 응답에 내부 구현 상세/스택트레이스 노출 금지
- 서로 다른 실패 원인을 단일 에러 코드로 뭉뚱그려 반환 금지
