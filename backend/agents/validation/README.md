# Validation Agent

## 역할

`ValidationAgent`는 최종 심사 결과가 공개 계약과 내부 정합성을 만족하는지 검사하고, 결과를 Langfuse score로도 남깁니다.

## 현재 입력

- `request_id`
- `company_name`
- `corp_name`
- `corp_code`
- `decision`
- `credit_grade`
- `decision_confidence`
- `decision_reasons`
- `recommended_limit`
- `explanation`
- `report`

## 현재 출력

- `validation_result`

`validation_result` 내부 주요 필드:

- `validation_passed`
- `pass_rate`
- `passed_checks`
- `total_checks`
- `failed_checks`
- `checks`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 검증 항목 예시

- `decision` 값 유효성
- `credit_grade` 존재 여부
- `report` 존재 여부
- `report.company_name`, `corp_name`, `corp_code` 일치 여부
- `report.summary`, `report.recommendation` 존재 여부
- `reject`면 `recommended_limit == 0`

## 상태 규칙

- 모든 검증이 통과하면 `status=success`
- 하나라도 실패하면 `status=partial`, `error_code=VALIDATION_WARNING`

## 관측성

Langfuse 활성화 시 아래 score를 기록합니다.

- `validation_pass_rate`
- `workflow_contract_valid`
- `failed_check_count`

## 테스트

```bash
.venv/bin/pytest tests/unit/test_validation_agent.py -q
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
```
