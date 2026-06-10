# Testing Conventions

## 목적

워크플로우 회귀를 빠르게 감지하고, agent 간 계약이 깨지지 않도록 보장한다.

## 테스트 범위

### Unit

- 대상: handler, utility, repository helper, 설정/계약 함수
- 외부 의존성은 mocking 한다
- 빠르고 결정론적으로 유지한다

### Integration

- 대상: orchestrator와 다수 agent 조합
- 그래프 의존 관계와 context 병합을 검증한다
- `continue_on_error` on/off 동작을 검증한다
- `steps` 공통 메타데이터를 검증한다

### API

- 대상: FastAPI 엔드포인트 계약
- `request_id` 헤더/응답 연동
- `400`/`500` 오류 매핑
- `company_name` 입력 검증을 확인한다

### CLI / Manual

- shell 스크립트와 DB 구축 CLI를 검증한다
- 외부 API를 직접 치는 검증은 `tests/manual/`에 둔다

## 현재 필수 시나리오

- 정상 흐름: `status=success`
- 대상 기업 미존재: `status=not_target`
- 일부 step 실패 + 기본 정책: downstream 중단, 최종 `status=partial`
- 일부 step 실패 + `continue_on_error=True`: 후속 단계 지속, 최종 `status=partial`
- 빈/공백 `company_name`: API `400`
- 모든 step에 `status`, `error_code`, `fallback_used`, `latency_ms` 존재

주의:

- 현재 공개 workflow 상태값에는 `not_configured`가 없다.
- agent 단위 `partial`은 존재하지만, 전체 workflow 상태는 `step.ok` 기준으로 계산된다.

## 디렉터리 규칙

- `tests/unit/`
- `tests/integration/`
- `tests/api/`
- `tests/cli/`
- `tests/manual/`

파일명:

- `test_<target>.py`

함수명:

- `test_<condition>_<expected>`

## 작성 규칙

- Arrange-Act-Assert 패턴 유지
- 테스트 하나는 하나의 기대 동작에 집중
- flaky test 금지
- 버그 수정 시 회귀 테스트 추가

## 실행 명령

```bash
./tests/run_all_tests.sh
.venv/bin/pytest -o cache_dir=.cache/pytest tests/
.venv/bin/pytest -q tests/
```

## 품질 게이트

```bash
.venv/bin/ruff check backend frontend tests
.venv/bin/pytest -o cache_dir=.cache/pytest tests/
```

현재 프론트엔드는 Streamlit 앱이므로 별도 `npm run lint` 게이트는 적용되지 않는다.
