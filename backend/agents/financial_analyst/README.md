# Financial Analyst Agent

## 역할

`FinancialAnalystAgent`는 `corp_code` 기준으로 재무 데이터와 재무 리스크 지표를 계산하는 오케스트레이터용 agent입니다. 현재 구현은 LLM agent 프레임워크가 아니라 provider + tool runtime 조합으로 동작합니다.

## 현재 입력

- `corp_code` (required)
- `company_name` (optional, logging용)
- `target_year` (optional, 기본 `2024`)
- `request_id` (optional)

## 현재 출력

- `financial_statements`
- `financial_ratios`
- `company_ratios`
- `altman_z`
- `financial_trend`
- `financial_flags`
- `risk_filters`
- `grade_cap`
- `financial_summary`
- `financial_tool_runs`
- `financial_tool_errors`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 내부 처리 순서

1. `get_financial_statements`
2. `calc_financial_ratios`
3. `calc_altman_z_prime`
4. `trend_analysis`
5. `apply_risk_filters`

각 단계는 `backend/common/tool_runtime.py`를 통해 fallback 가능하게 실행됩니다.

## 상태 규칙

- 모든 도구가 정상 동작하면 `status=success`
- 일부 도구가 fallback을 사용하면 `status=partial`
- `corp_code`가 없으면 `ValueError`

## 의존성

- `DatabaseFinancialDataProvider`
- `backend/tools/financial.py`
- `OPEN_DART_API_KEY` 일부 기능 사용

## 오케스트레이터 연동

- agent 이름: `financial_analyst`
- 시작 분석 노드로 실행됩니다
- `IndustryAnalystAgent`가 이 agent의 `financial_ratios`를 downstream 입력으로 사용합니다
- `DecisionAgent`는 `grade_cap`, 재무 요약 값을 활용합니다

## 테스트

```bash
.venv/bin/pytest tests/integration/test_agent_tool_fallbacks.py -q
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
```
