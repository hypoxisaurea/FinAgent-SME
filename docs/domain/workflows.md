# Credit Assessment Workflow

## 목적

본 문서는 현재 구현된 FinAgent-SME 신용 심사 워크플로우를 설명한다. 기준 흐름은 `Streamlit UI -> FastAPI Job API -> Workflow Job Runner -> WorkflowOrchestrator -> Agent Graph -> Report/Validation`이다.

## 참여 Agent

- `CompanyResolverAgent`: 기업 마스터와 기업개황을 조회해 대상 기업 여부를 판별한다.
- `NewsCollectorAgent`: 뉴스 수집/요약/적재와 downstream용 `news_data`를 만든다.
- `FinancialAnalystAgent`: 재무제표, 비율, 추세, `grade_cap`을 계산한다.
- `IndustryAnalystAgent`: KSIC 매핑, 산업 평균, 업황, 경기, 거시 지표를 계산한다.
- `RiskEventAgent`: 뉴스 기반 리스크 이벤트를 분류하고 집계한다.
- `DecisionAgent`: 심사 결정, 등급, 추천 한도, 설명을 생성한다.
- `ReportAgent`: 최종 리포트를 생성한다.
- `ValidationAgent`: 결과 정합성을 검증하고 Langfuse score를 기록한다.
- `MultiModalDocumentAgent`: 내부 payload에 `pdf_path`가 있을 때만 실행된다.

## 공개 입력 계약

현재 공개 HTTP API의 요청 스키마는 아래와 같다.

- `company_name` (`string`, required)

주의:

- `pdf_path`, `continue_on_error`는 내부 워크플로우 확장 포인트로는 존재하지만 현재 공개 API 스키마에는 없다.
- 공백만 있는 `company_name`은 API 계층에서 `400 INVALID_INPUT`으로 처리된다.

## 공개 Job API 계약

현재 프론트엔드 기본 흐름은 아래 3개 엔드포인트를 사용한다.

- `POST /api/v1/workflows/jobs`
- `GET /api/v1/workflows/jobs/{job_id}`
- `GET /api/v1/workflows/jobs/{job_id}/result`

호환용 동기 엔드포인트도 유지된다.

- `POST /api/v1/workflows/orchestrator`
- `POST /api/v1/workflows/credit-assessment`

## 최종 응답 계약

### 일반 응답

- `request_id`
- `company_name`
- `status`
- `context`
- `steps`

### `not_target` 추가 필드

- `code`
- `message`

### `context` 주요 예시

- `corp_code`
- `corp_name`
- `company_profile`
- `news_data`
- `financial_ratios`
- `grade_cap`
- `industry_summary`
- `overall_risk_level`
- `decision`
- `credit_grade`
- `recommended_limit`
- `report`
- `validation_result`

### `steps[*]` 주요 필드

- `agent_name`
- `ok`
- `status`
- `error_code`
- `fallback_used`
- `latency_ms`
- `output`
- `error`

## 현재 실행 순서

1. **Job 접수**
   - 프론트가 `company_name`으로 `POST /api/v1/workflows/jobs`를 호출한다.
   - 서버는 `request_id`를 생성하거나 헤더 값을 사용한다.
   - 서버는 `job_id`를 발급하고 DB에 `queued` 상태로 저장한다.

2. **Job 실행 시작**
   - `workflow_job_runner`가 queued job을 claim 해 `running`으로 바꾼다.
   - runner가 background thread에서 `run_credit_workflow()`를 실행한다.

3. **기업 식별**
   - `CompanyResolverAgent`가 `sme_list`를 조회한다.
   - 필요 시 `company_profiles`를 병합해 `company_profile`을 구성한다.
   - 기업이 없으면 `status=not_target`으로 종료한다.

4. **시작 분석 노드**
   - `NewsCollectorAgent`
   - `FinancialAnalystAgent`
   - 내부 payload에 `pdf_path`가 있을 때 `MultiModalDocumentAgent`

5. **의존 분석 노드**
   - `RiskEventAgent`는 `news_collector` 이후 실행된다.
   - `IndustryAnalystAgent`는 `financial_analyst` 이후 실행된다.

6. **후속 심사 단계**
   - `DecisionAgent`
   - `ReportAgent`
   - `ValidationAgent`

7. **결과 저장**
   - 오케스트레이터가 최종 `context`와 `steps`를 조립해 반환한다.
   - runner가 workflow 결과와 `step_summary`를 저장하고 job을 `succeeded` 또는 `failed`로 마감한다.

8. **상태 조회 및 결과 fetch**
   - 프론트는 `GET /api/v1/workflows/jobs/{job_id}`로 상태를 polling 한다.
   - `status=succeeded`가 되면 `/result`에서 최종 workflow 결과를 가져온다.

## 상태값 규칙

- `not_target`: 기업 미존재
- `success`: 모든 step이 `ok=True`
- `partial`: 성공 step과 실패 step이 혼재
- `failed`: 모든 step이 `ok=False`

주의:

- agent의 `status=partial` 또는 `fallback_used=true`는 step 내부 메타데이터다.
- 현재 전체 workflow `status`는 `step.ok` 집계로만 계산된다.

## 실패 처리 정책

- 기본 정책은 `fail-fast`
- `continue_on_error=True`로 오케스트레이터를 만들면 실패 step이 있어도 후속 단계 지속 가능
- 공개 HTTP API는 현재 `continue_on_error` 토글을 직접 노출하지 않음
- 내부 예외는 API 계층에서 `500 AGENT_EXECUTION_FAILED`로 매핑

## Job 상태 정책

- `queued`: 접수 완료, 미실행
- `running`: worker가 claim 후 실행 중
- `succeeded`: workflow 결과 저장 완료
- `failed`: 입력 오류 또는 실행 오류로 종료

## 관측성

- 모든 요청은 `request_id`를 가진다.
- 워크플로우와 agent 단위 로그가 남는다.
- Langfuse가 활성화된 경우 trace/observation/score가 기록된다.
- 테스트 런타임에서는 기본적으로 Langfuse가 비활성화된다.
