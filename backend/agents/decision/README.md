# Decision Agent

## 역할

`DecisionAgent`는 재무, 산업, 리스크 신호를 종합해 승인 여부, 신용등급, 추천 한도, 설명을 산출합니다.

## 현재 입력

- `company_name`
- `corp_code`
- `critical_count`
- `high_count`
- `medium_count`
- `low_count`
- `overall_risk_level`
- `latest_debt_ratio`
- `latest_op_margin`
- `is_net_income_negative`
- `grade_cap`
- `total_assets`
- `revenue`
- `avg_revenue_last_3y`
- `classified_events`

## 현재 출력

- `decision`
- `credit_grade`
- `credit_score`
- `decision_confidence`
- `decision_reasons`
- `recommended_limit`
- `limit_range`
- `limit_basis`
- `explanation`
- `grade_detail`
- `processing_errors`
- `processed_at`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 내부 처리

1. `grade_calculator`
2. `decision_maker`
3. `limit_recommender`
4. `explanation_generator`

최종 결과는 `DecisionOutput` 기반으로 조립되며, 오케스트레이터와 리포트가 바로 쓸 수 있도록 주요 필드는 최상위 키로도 노출됩니다.

## 상태 규칙

- 처리 오류가 없으면 `status=success`
- `processing_errors` 또는 설명 fallback이 있으면 `status=partial`
- 결과 객체가 없으면 `status=failed`, `error_code=DECISION_OUTPUT_MISSING`

## 오케스트레이터 연동

- agent 이름: `decision`
- `risk_event`, `industry_analyst`, `financial_analyst` 이후 후속 심사 단계로 실행됩니다.
- `ReportAgent`, `ValidationAgent`가 이 결과를 downstream으로 사용합니다.

## 테스트

```bash
.venv/bin/pytest tests/unit/test_decision_handlers.py -q
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
```
