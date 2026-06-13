# Company Resolver Agent

## 역할

`CompanyResolverAgent`는 입력된 회사명이 현재 심사 대상 기업인지 판별하고, downstream이 사용할 식별 정보를 붙이는 첫 단계 agent입니다.

## 현재 입력

- `company_name` (required)

## 현재 출력

대상 기업인 경우:

- `company_found`
- `corp_code`
- `corp_name`
- `company_profile`
- `company_resolution`

대상 기업이 아닌 경우:

- `company_found`
- `workflow_status`
- `workflow_code`
- `workflow_message`
- `company_resolution`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 상태 규칙

- 매칭 성공 시 `status=success`
- 대상 기업이 아니어도 예외가 아니라 정상 응답이며 `company_found=False`
- `company_name`이 비어 있으면 `ValueError`

## 오케스트레이터 연동

- agent 이름: `company_resolver`
- 모든 심사 워크플로우의 첫 단계입니다.
- `company_found=False`이면 workflow는 `status=not_target`으로 종료됩니다.

## 테스트

```bash
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
.venv/bin/pytest tests/api/test_workflows_api.py -q
```
