# Workflow Orchestrator

## 역할

`WorkflowOrchestrator`는 개별 agent를 그래프 형태로 조합해 실행 순서, 실패 전파, 최종 workflow 응답 조립을 담당합니다.

## 주요 진입점

- `create_credit_workflow()`
- `run_credit_workflow()`
- `WorkflowOrchestrator.run()`

## 현재 입력

공개 기본 입력:

- `company_name` (required)

내부 확장 입력:

- `request_id`
- `collect_sources`
- `pdf_path`
- `continue_on_error`
- `target_year`
- agent별 timeout/retry 관련 payload

## 현재 출력

- `request_id`
- `company_name`
- `status`
- `code`
- `message`
- `context`
- `steps`

## 기본 실행 순서

1. `CompanyResolverAgent`
2. 병렬 시작 노드
3. 의존 노드
4. `DecisionAgent`
5. `ReportAgent`
6. `ValidationAgent`

Validation 실패 시 기본 1회 `ReportAgent -> ValidationAgent`를 재실행한다. 재시도
소진 후에는 `VALIDATION_FAILED`로 종료하고 최종 판단/보고서를 응답에서 차단한다.

### Validation 후속 처리 규칙

| 조건 | gate 상태 | 다음 처리 |
| --- | --- | --- |
| validation step이 성공하고 `validation_passed=true` | `passed` | 결과 공개 후 종료 |
| 검증 실패이고 재시도 횟수가 남음 | `retrying` | `report` 재생성 후 `validation` 재실행 |
| 검증 실패이고 재시도 횟수를 소진함 | `blocked` | `failed / VALIDATION_FAILED`로 종료하고 결과 차단 |
| validation 실행/계약 오류 또는 step/result 상태 불일치 | `retrying` 또는 `blocked` | 검증 실패로 정규화하여 동일한 재시도/차단 정책 적용 |

`report`가 validation 바로 앞 노드가 아니면 재생성할 노드가 없으므로 재시도 횟수를
`0`으로 강제하고 즉시 `blocked` 처리한다. `continue_on_error=True`여도 validation
gate에는 적용되지 않으며, 차단된 판단·한도·보고서는 `context`와 `steps[].output`
모두에서 제거한다.

`pdf_path`가 있으면 `MultiModalDocumentAgent`가 병렬 노드에 추가됩니다.

## 상태 규칙

- `not_target`: resolver가 대상 기업이 아니라고 판단
- `success`: 유효 step이 모두 `ok=True`
- `partial`: 성공/실패 step 혼재
- `failed`: 모든 step이 실패했거나 validation gate가 결과를 차단

주의:

- agent의 `status=partial`은 step 내부 메타데이터입니다.
- 전체 workflow `status`는 `step.ok` 집계 기준입니다. 단, 재검증이 통과하면 이전
  validation 실패 step은 이력에 유지하되 상태 집계에서는 제외합니다.

## 관측성

- `request_id` 기반 구조화 로그
- Langfuse observation/trace 연동
- step 요약 집계는 job status API에서도 재사용됩니다

## 테스트

```bash
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
.venv/bin/pytest tests/api/test_workflows_api.py -q
.venv/bin/pytest tests/api/test_workflow_jobs_api.py -q
```
