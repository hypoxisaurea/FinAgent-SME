# Industry Analyst Agent

## 역할

`IndustryAnalystAgent`는 기업의 업종과 거시 환경을 분석해 재무 결과를 산업 맥락 안에서 해석하는 오케스트레이터용 agent입니다. 현재 구현은 provider 기반 동기/비동기 도구 호출을 감싼 구조입니다.

## 현재 입력

- `corp_code` (required)
- `financial_ratios` (optional but 권장)
- `company_name` (optional)
- `target_year` (optional, 기본 `2024`)
- `request_id` (optional)

## 현재 출력

- `ksic_code`
- `industry_summary`
- `industry_outlook`
- `business_cycle`
- `macro_indicators`
- `peer_comparison`
- `industry_tool_runs`
- `industry_tool_errors`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 내부 처리 순서

1. `map_corp_to_ksic`
2. `get_industry_avg_ratios`
3. `get_industry_outlook`
4. `get_business_cycle`
5. `get_macro_indicators`

도구 실패 시 기본 중립값이나 안내 문구로 fallback 합니다.

## 데이터 소스

- OpenDART: 업종 코드 조회
- ECOS: 기준금리, 경기 지표
- KOSIS: 업황 지표
- 로컬 CSV: 산업 평균 재무비율

## 상태 규칙

- 모든 도구 성공 시 `status=success`
- 일부 도구 fallback 시 `status=partial`
- `corp_code` 누락 시 `ValueError`

## 오케스트레이터 연동

- agent 이름: `industry_analyst`
- `financial_analyst` 이후 의존 노드로 실행됩니다
- `DecisionAgent`는 `industry_summary`, `peer_comparison`, `macro_indicators`를 활용합니다

## 테스트

```bash
.venv/bin/pytest tests/integration/test_agent_tool_fallbacks.py -q
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
```
