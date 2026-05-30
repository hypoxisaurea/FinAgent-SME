# Tests

`tests/`는 FinAgent-SME의 자동화 테스트와 수동 검증 산출물을 함께 보관하는 디렉터리입니다. 기본 원칙은 다음과 같습니다.

- `pytest`로 돌아가는 결정론적 회귀 테스트는 `test_*.py`
- 외부 API 확인처럼 수동 실행이 필요한 파일은 `manual_*.py`
- 공통 테스트 부트스트랩은 `tests/conftest.py`

## 현재 파일 구성

### 자동화 테스트

- `test_workflows_api.py`
- `test_workflow_orchestrator.py`
- `test_decision_handlers.py`
- `test_risk_event_handlers.py`
- `test_final_pipeline.py`
- `test_build_db_script.py`
- `test_collector_database_config.py`
- `test_logging_config.py`
- `test_opendartreader_shim.py`
- `test_sme_repository.py`
- `test_scripts_cli.py`

### 수동 검증

- `manual_financial_industry_agents_tools.py`
- `manual_results_financial_industry_tools.md`

### 실행 스크립트

- `run_all_tests.sh`

## 자동화 테스트

자동화 테스트는 기능별로 분리되어 있습니다.

- API 계약: `test_workflows_api.py`
- 오케스트레이터 흐름: `test_workflow_orchestrator.py`
- 의사결정/리스크 핸들러: `test_decision_handlers.py`, `test_risk_event_handlers.py`
- 통합 시나리오: `test_final_pipeline.py`
- 배치/설정/인프라: `test_build_db_script.py`, `test_collector_database_config.py`, `test_logging_config.py`
- 어댑터/리포지토리: `test_opendartreader_shim.py`, `test_sme_repository.py`
- 공개 셸 스크립트: `test_scripts_cli.py`

실행:

```bash
./tests/run_all_tests.sh
```

전체 실행:

```bash
.venv/bin/pytest tests/
```

## 수동 검증 스크립트

### `manual_financial_industry_agents_tools.py`

- 재무/산업 분석 도구를 실제 API 데이터로 확인하는 스크립트
- `pytest` 스타일의 결정론적 단위 테스트라기보다, 로컬 수동 점검용에 가깝습니다.
- `backend/.env`에 API 키가 필요할 수 있습니다.
- 출력은 콘솔 로그로 확인합니다.

실행:

```bash
./tests/run_all_tests.sh --with-manual
.venv/bin/python tests/manual_financial_industry_agents_tools.py
```

### `manual_results_financial_industry_tools.md`

- 위 수동 스크립트 실행 결과 예시를 정리한 문서

## 테스트 작성 원칙

- 새 기능에는 회귀 테스트를 추가합니다.
- 버그 수정 시 실패 재현 테스트를 먼저 고려합니다.
- 외부 API, DB, 파일 의존은 가능하면 mocking 합니다.
- 테스트 규칙의 기준 문서는 `docs/conventions/testing.md`입니다.

## 품질 확인

```bash
./tests/run_all_tests.sh
.venv/bin/pytest tests/
.venv/bin/ruff check backend tests
```

저장소 전체 `ruff` 상태와 별개로, 변경한 테스트 파일 기준으로는 lint를 함께 확인하는 것을 권장합니다.
