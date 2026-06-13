# Tests

`tests/`는 FinAgent-SME의 자동화 테스트와 수동 검증 자료를 보관한다.

## 디렉터리 구조

```text
tests/
├── api/
├── cli/
├── integration/
├── manual/
├── unit/
├── conftest.py
├── clean_test_cache.sh
└── run_all_tests.sh
```

## 현재 자동화 테스트 범위

### API

- `api/test_workflows_api.py`
  - 워크플로우 엔드포인트 호출
  - `request_id` 헤더/응답 검증
  - `400`/`500` 오류 응답 검증

### Integration

- `integration/test_workflow_orchestrator.py`
- `integration/test_agent_tool_fallbacks.py`
- `integration/test_final_pipeline.py`

검증 포인트:

- 그래프 의존 관계
- `not_target`, `success`, `partial`
- fallback 및 `steps` 메타데이터

### Unit

- `unit/test_validation_agent.py`
- `unit/test_decision_handlers.py`
- `unit/test_risk_event_handlers.py`
- `unit/test_repositories.py`
- `unit/test_dart_client.py`
- `unit/test_economic_data_client.py`
- `unit/test_langfuse_config.py`
- `unit/test_logging_config.py`
- `unit/test_build_db_script.py`
- `unit/test_company_registry_pipeline_service.py`
- `unit/test_collector_database_config.py`
- `unit/test_opendartreader_shim.py`

### CLI

- `cli/test_scripts_cli.py`

## 수동 검증

- `manual/manual_financial_industry_agents_tools.py`
- `manual/manual_results_financial_industry_tools.md`

수동 검증은 외부 API 키와 네트워크가 필요한 점검용이다.

## 캐시 정책

- `pytest` 캐시는 `.cache/pytest/` 사용
- `run_all_tests.sh` 실행 후 `clean_test_cache.sh`로 정리
- `__pycache__`, `.pytest_cache`, `.cache`는 커밋하지 않는다

## 실행

전체 자동화 테스트:

```bash
./tests/run_all_tests.sh
```

직접 실행:

```bash
.venv/bin/pytest -o cache_dir=.cache/pytest tests/
```

수동 검증 포함:

```bash
./tests/run_all_tests.sh --with-manual
```

## 품질 확인

```bash
.venv/bin/ruff check backend frontend tests
.venv/bin/pytest -o cache_dir=.cache/pytest tests/
```

현재 프론트는 Streamlit 앱이므로 JavaScript lint 단계는 없다.
