# Credit Assessment Workflow

## 목적

본 문서는 FinAgent-SME의 목표 신용 심사 워크플로우를 정의한다.
기준 흐름은 `Frontend -> Orchestrator -> 대상 기업 판별 -> 병렬 분석 Agent -> Decision Agent -> Report Agent` 이다.

## 참여 Agent

- `Company Resolver`: 기업명으로 대상 기업 여부를 판별하고 `corp_code`, `corp_name`을 확보한다.
- `Collector Agent`: 뉴스 등 원천 데이터를 수집한다.
- `Financial Analyst Agent`: 재무 지표, 재무 추세, 등급 상한(`grade_cap`)을 분석한다.
- `Industry Analyst Agent`: 산업 평균, 업황, 경기 국면, 거시환경을 분석한다.
- `Multimodal Document Agent`: 문서/PDF/비정형 자료를 분석한다.
- `Risk Event Agent`: 뉴스·공시·법적·재무 이상 징후를 탐지하고 리스크 수준을 집계한다.
- `Decision Agent`: 병합된 분석 결과를 바탕으로 심사 결정을 내린다.
- `Report Agent`: 최종 심사 리포트를 생성한다.

## 입력/출력 계약

### 입력

- `company_name` (string, required)
- `request_id` (string, optional, 없으면 서버 생성)
- `pdf_path` (string, optional)
- `extra_payload` (object, optional)

### 기업 식별 단계 출력

- `company_name` (string)
- `corp_name` (string)
- `corp_code` (string)

기업이 대상 테이블에 없으면 아래 형태로 즉시 종료한다.

- `status`: `not_target`
- `code`: `COMPANY_NOT_FOUND`
- `message`: `대상 기업이 아닙니다.`
- `detail.company_name`: 요청 기업명

### 최종 출력

- `status` (`success` | `partial` | `failed` | `not_target`)
- `company_name` (string)
- `corp_name` (string)
- `corp_code` (string)
- `decision` (object)
  - `result` (`approve` | `review` | `reject`)
  - `confidence` (0.0 ~ 1.0)
  - `reasons` (string[])
- `report` (object)
- `steps` (단계별 실행 결과 목록)
- `context` (중간 산출물)

## 표준 실행 순서

1. **요청 수신**
   - Frontend가 기업명을 입력해 Orchestrator API를 호출한다.
   - API는 입력 유효성을 검증한다.
   - `company_name` 공백 제거 후 비어 있으면 실패 처리한다.

2. **Orchestrator 초기화**
   - 공통 컨텍스트(`company_name`, `request_id`, `timestamp`)를 생성한다.
   - 대상 기업 판별 단계를 먼저 실행한다.

3. **대상 기업 판별**
   - Orchestrator는 Collector가 구축한 기업 마스터 테이블을 조회한다.
   - 조회 기준은 `company_name`이다.
   - 조회 결과가 있으면 `corp_code`, `corp_name`을 컨텍스트에 적재한다.
   - 조회 결과가 없으면 워크플로우를 즉시 종료한다.
   - Frontend에는 `not_target` 상태와 표준 오류 메시지를 반환한다.

4. **병렬 분석 단계**
   - 대상 기업으로 판별된 경우 아래 Agent를 병렬 실행한다.
   - `Collector Agent` : 대상 기업 뉴스 조회
   - `Financial Analyst Agent` : 재무 분석
   - `Industry Analyst Agent` : 산업/거시 분석
   - `Multimodal Document Agent` : 문서 분석
   - `Risk Event Agent` : 리스크 이벤트 분석
   - 각 Agent 출력은 `dict` 형태로 정규화한다.
   - 문서 입력이 없는 경우 `Multimodal Document Agent`는 `skipped` 상태로 종료할 수 있다.

5. **결과 병합**
   - Orchestrator가 병렬 Agent 산출물을 `context`에 병합한다.
   - 공통 식별 키(`company_name`, `corp_name`, `corp_code`)는 덮어쓰지 않는다.
   - 충돌 키는 사전 정의한 우선순위 규칙에 따라 병합한다.

6. **Decision 단계**
   - `Decision Agent`가 병합된 컨텍스트를 입력받아 신용등급, 승인/보류/거절, 추천 한도를 산출한다.
   - 주요 입력은 재무 분석 결과, 산업 분석 결과, 문서 분석 결과, 리스크 이벤트 요약이다.

7. **Report 단계**
   - `Report Agent`가 `Decision Agent` 결과와 중간 분석 결과를 바탕으로 최종 심사 리포트를 생성한다.
   - 리포트에는 심사 요약, 핵심 리스크, 근거, 권고안이 포함된다.

8. **응답 반환**
   - Orchestrator는 `status`, `decision`, `report`, `steps`, `context`를 포함한 표준 응답을 반환한다.

## 컨텍스트 규약

### 대상 기업 식별 컨텍스트

- `company_name`
- `corp_name`
- `corp_code`

### 병렬 분석 컨텍스트 예시

- `news_data`
- `financial_summary`
- `financial_ratios`
- `grade_cap`
- `industry_summary`
- `peer_comparison`
- `document_summary`
- `document_risk_factors`
- `overall_risk_level`
- `critical_count`
- `high_count`
- `medium_count`
- `low_count`

### Decision 출력 컨텍스트 예시

- `credit_grade`
- `credit_score`
- `decision`
- `decision_confidence`
- `decision_reasons`
- `recommended_limit`

## 실패 처리 정책

- 기본 정책은 `fail-fast`이다.
- 단, 대상 기업 미존재는 예외가 아니라 정상 종료 상태 `not_target`으로 처리한다.
- 설정값 `continue_on_error=true`인 경우 병렬 분석 단계와 후속 단계에서 부분 성공(`partial`)을 허용한다.
- Agent 실패 시에도 실패한 단계 정보(`agent_name`, `error`)는 반드시 `steps`에 남긴다.
- 핵심 입력(`company_name`) 오류는 즉시 요청 실패 처리한다.

## 상태값 규칙

- `success`: 실행된 모든 필수 단계 성공
- `partial`: 일부 분석 단계 실패, 일부 성공
- `failed`: 필수 단계 실행 실패
- `not_target`: 기업 마스터 테이블에 대상 기업이 없음

## 구현 메모

- 모든 Agent는 `Agent` 프로토콜(`name`, `async run(payload) -> dict`)을 준수해야 한다.
- Orchestrator는 대상 기업 판별 단계와 병렬 분석 단계를 분리해서 관리한다.
- 병렬 분석 단계는 `asyncio.gather()` 또는 동등한 병렬 실행 구조로 구현한다.
- Agent 반환 타입이 `dict`가 아니면 타입 오류로 처리한다.
- 각 단계 결과는 추적 가능하도록 `steps`에 남긴다.
- 기업 마스터 테이블은 최소 `corp_code`, `corp_name`을 포함해야 한다.
