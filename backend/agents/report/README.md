# Report Agent

## 역할

`ReportAgent`는 심사 결론과 중간 분석 결과를 사람이 읽기 쉬운 최종 리포트 형태로 정리합니다.

## 현재 입력

- `company_name`
- `corp_name`
- `corp_code`
- `decision`
- `credit_grade`
- `decision_confidence`
- `decision_reasons`
- `recommended_limit`
- `overall_risk_level`
- `explanation`

## 현재 출력

- `report`

`report` 내부 주요 필드:

- `company_name`
- `corp_name`
- `corp_code`
- `generated_at`
- `decision`
- `credit_grade`
- `confidence`
- `recommended_limit`
- `summary`
- `key_risks`
- `recommendation`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 상태 규칙

- 설명 필드가 모두 있으면 `status=success`
- `summary` 또는 `recommendation`을 fallback 문구로 생성하면 `fallback_used=true`
- fallback 발생 시 `error_code=REPORT_FALLBACK_USED`

## 오케스트레이터 연동

- agent 이름: `report`
- `DecisionAgent` 이후 실행됩니다.
- `ValidationAgent`가 이 agent의 `report`를 검증 입력으로 사용합니다.

## 테스트

```bash
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
.venv/bin/pytest tests/unit/test_validation_agent.py -q
```
