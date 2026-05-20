# Tests

`tests/`는 FinAgent-SME의 자동화 테스트와 수동 검증 산출물을 함께 보관하는 디렉터리입니다. 현재는 `pytest` 기반 API/설정 회귀 테스트와, 외부 API를 실제로 호출해 보는 수동 확인 스크립트가 같이 존재합니다.

## 현재 파일 구성

- `test_workflows_api.py`
- `test_collector_database_config.py`
- `test_financial_industry_agents_tools.py`
- `test_results_financial_industry_tools.md`

## 자동화 테스트

### `test_workflows_api.py`

- FastAPI 엔드포인트 계약 테스트
- `/api/v1/workflows/orchestrator`
- `/api/v1/workflows/credit-assessment`
- 정상 응답, `400`, `500` 매핑 검증

### `test_collector_database_config.py`

- collector DB 설정 관련 단위 테스트
- `backend/.env` 경로 해석
- `DATABASE_URL` 우선순위
- `POSTGRES_*` 값으로 URL 생성

실행:

```bash
.venv/bin/pytest tests/test_workflows_api.py
.venv/bin/pytest tests/test_collector_database_config.py
```

전체 실행:

```bash
.venv/bin/pytest tests/
```

## 수동 검증 스크립트

### `test_financial_industry_agents_tools.py`

- 재무/산업 분석 도구를 실제 API 데이터로 확인하는 스크립트
- `pytest` 스타일의 결정론적 단위 테스트라기보다, 로컬 수동 점검용에 가깝습니다.
- `backend/.env`에 API 키가 필요할 수 있습니다.
- 출력은 콘솔 로그로 확인합니다.

실행:

```bash
.venv/bin/python tests/test_financial_industry_agents_tools.py
```

### `test_results_financial_industry_tools.md`

- 위 수동 스크립트 실행 결과 예시를 정리한 문서

## 테스트 작성 원칙

- 새 기능에는 회귀 테스트를 추가합니다.
- 버그 수정 시 실패 재현 테스트를 먼저 고려합니다.
- 외부 API, DB, 파일 의존은 가능하면 mocking 합니다.
- 테스트 규칙의 기준 문서는 `docs/conventions/testing.md`입니다.

## 품질 확인

```bash
.venv/bin/pytest tests/
.venv/bin/ruff check backend tests
```

저장소 전체 `ruff` 상태와 별개로, 변경한 테스트 파일 기준으로는 lint를 함께 확인하는 것을 권장합니다.

## 참고 문서

- [README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/README.md)
- [backend/README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/backend/README.md)
- [docs/conventions/testing.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/docs/conventions/testing.md)
