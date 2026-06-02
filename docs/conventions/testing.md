# Testing Conventions

## 목적

워크플로우 변경 시 기능 회귀를 방지하고, 심사 결과의 일관성을 보장한다.

## 테스트 범위

### 1) 단위 테스트 (Unit)

- 대상: Agent 단일 로직, 유틸 함수, 상태 계산 함수
- 외부 의존성(DB, API, 파일, LLM)은 mocking 한다
- 빠르고 결정론적인 테스트를 작성한다

### 2) 통합 테스트 (Integration)

- 대상: Orchestrator + 다수 Agent 조합
- 병렬 단계 결과 병합, 상태값 계산, 실패 전파를 검증한다
- `continue_on_error` on/off 시나리오를 모두 검증한다
- 각 단계 결과에 `status`, `error_code`, `fallback_used`, `latency_ms`가 남는지 검증한다

### 3) API 테스트

- 대상: FastAPI 엔드포인트 입력/출력 계약
- 유효 입력, 무효 입력, 내부 오류 매핑(4xx/5xx)을 검증한다
- 응답 스키마 및 에러 포맷 일관성을 검증한다

## 필수 테스트 시나리오

- 정상 흐름: 전체 단계 성공 시 `status=success`
- 부분 실패 흐름: 일부 Agent 실패 + `continue_on_error=true` 시 `status=partial`
- 실패 흐름: 핵심 단계 실패 시 `status=failed`
- 미구성 흐름: Agent 미등록 시 `status=not_configured`
- 입력 검증: 빈 `company_name` 요청 실패
- 공통 실패 계약: 모든 step에 실행 메타데이터 존재

## 파일/네이밍 규칙

- 테스트 위치: `tests/`
- 권장 하위 폴더:
  - `tests/unit/`
  - `tests/integration/`
  - `tests/api/`
  - `tests/cli/`
  - `tests/manual/`
- 파일명: `test_<target>.py`
- 함수명: `test_<condition>_<expected>`

예시:
- `test_orchestrator_all_steps_success`
- `test_orchestrator_partial_when_one_agent_fails`

## 작성 규칙

- Arrange-Act-Assert 패턴을 유지한다
- 테스트 하나는 하나의 기대 동작만 검증한다
- flaky test 금지 (시간/외부 상태 의존 최소화)
- 버그 수정 시 회귀 테스트를 반드시 추가한다

## 실행 명령

- 전체 테스트: `pytest tests/`
- 빠른 확인(선택): `pytest tests/ -q`

## PR 품질 게이트

- 새 기능에는 테스트를 반드시 포함한다
- 기존 기능 변경 시 영향 범위 테스트를 갱신한다
- 최소 체크:
  - `ruff check backend`
  - `cd frontend && npm run lint`
  - `pytest tests/`
