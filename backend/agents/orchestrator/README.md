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

`pdf_path`가 있으면 `MultiModalDocumentAgent`가 병렬 노드에 추가됩니다.

## 상태 규칙

- `not_target`: resolver가 대상 기업이 아니라고 판단
- `success`: 모든 step의 `ok=True`
- `partial`: 성공/실패 step 혼재
- `failed`: 모든 step의 `ok=False`

주의:

- agent의 `status=partial`은 step 내부 메타데이터입니다.
- 현재 전체 workflow `status`는 `step.ok` 집계 기준입니다.

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
