# Risk Event Agent

## 역할

`RiskEventAgent`는 뉴스, 공시, 법원 공고, 재무 이상 징후를 종합해 리스크 이벤트를 분류하고 심각도를 집계합니다.

## 현재 입력

- `company_name` (required)
- `corp_code` (required)
- `news_data` (optional)
- `disclosure_data` (optional)
- `court_data` (optional)
- `request_id` (optional)

## 현재 출력

- `keyword_result`
- `sentiment_result`
- `disclosure_result`
- `legal_result`
- `financial_result`
- `all_events`
- `classified_events`
- `timeline`
- `critical_count`
- `high_count`
- `medium_count`
- `low_count`
- `total_event_count`
- `overall_risk_level`
- `latest_debt_ratio`
- `latest_op_margin`
- `is_net_income_negative`
- `processing_errors`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 내부 처리

핵심 핸들러:

1. 키워드 탐지
2. 감성 분석
3. 공시 이상 탐지
4. 법적 리스크 탐지
5. 재무 이상 탐지
6. 심각도 분류
7. 타임라인 조립

## 상태 규칙

- 처리 오류가 없으면 `status=success`
- `processing_errors`가 있으면 `status=partial`, `error_code=RISK_SIGNAL_PARTIAL`

## 오케스트레이터 연동

- agent 이름: `risk_event`
- `news_collector` 이후 의존 노드로 실행됩니다.
- `DecisionAgent`가 `overall_risk_level`, 이벤트 카운트, 재무 이상 신호를 downstream으로 사용합니다.

## 테스트

```bash
.venv/bin/pytest tests/unit/test_risk_event_handlers.py -q
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
```
