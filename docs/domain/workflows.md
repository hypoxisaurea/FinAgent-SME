# Credit Assessment Workflow

## 목적

본 문서는 K-Credit Agent의 신용 심사 워크플로우를 정의한다.  
기준 흐름: `User -> Orchestrator -> (병렬 분석 Agent들) -> XAI/Decision Agent -> Report Agent`

## 참여 Agent

- `Collect Agent`: 기업 기본 정보/원천 데이터 수집
- `Financial Analyst Agent`: 재무 지표 분석
- `Risk Event Agent`: 이벤트/뉴스/이상 징후 분석
- `Multimodal Document Agent`: 문서/비정형 자료 분석
- `Industry Agent`: 산업/업종 맥락 분석
- `XAI/Decision Agent`: 결과 통합, 의사결정, 설명 가능성(XAI) 생성
- `Report Agent`: 최종 심사 리포트 생성

## 입력/출력 계약

### 입력

- `company_name` (string, required)
- `request_id` (string, optional, 없으면 서버 생성)
- `extra_payload` (object, optional)

### 최종 출력

- `status` (`success` | `partial` | `failed` | `not_configured`)
- `company_name` (string)
- `decision` (object)
  - `result` (`approve` | `review` | `reject`)
  - `confidence` (0.0 ~ 1.0)
  - `reasons` (string[])
- `risk_factors` (object[])
- `xai` (object)
- `report` (object)
- `steps` (단계별 실행 결과 목록)
- `context` (중간 산출물)

## 표준 실행 순서

1. **요청 수신**
   - API가 입력 유효성을 검증한다.
   - `company_name` 공백 제거 후 비어 있으면 실패 처리한다.
2. **Orchestrator 초기화**
   - 공통 컨텍스트(`company_name`, `request_id`, `timestamp`)를 생성한다.
   - 실행할 Agent 목록을 결정한다.
3. **병렬 분석 단계**
   - 아래 5개 Agent를 논리적으로 병렬 실행한다.
     - Collect
     - Financial Analyst
     - Risk Event
     - Multimodal Document
     - Industry
   - 각 Agent 출력은 `dict` 형태로 정규화한다.
4. **결과 병합**
   - Orchestrator가 Agent 산출물을 `context`에 병합한다.
   - 충돌 키는 사전 정의한 우선순위 규칙으로 병합한다.
5. **XAI/Decision 단계**
   - 통합 컨텍스트를 근거로 의사결정과 설명 가능성 결과를 생성한다.
6. **Report 단계**
   - 심사 요약, 리스크 요인, 근거, 권고를 포함한 리포트를 생성한다.
7. **응답 반환**
   - 표준 응답 스키마로 최종 결과를 반환한다.

## 실패 처리 정책

- 기본 정책은 `fail-fast`이다.
- 설정값 `continue_on_error=true`인 경우 부분 성공(`partial`)을 허용한다.
- Agent 실패 시에도 실패한 단계 정보(`agent_name`, `error`)는 반드시 `steps`에 남긴다.
- 핵심 입력(`company_name`) 오류는 즉시 요청 실패 처리한다.

## 상태값 규칙

- `success`: 실행된 모든 단계 성공
- `partial`: 일부 단계 실패, 일부 성공
- `failed`: 실행된 단계가 모두 실패
- `not_configured`: 실행 Agent가 등록되지 않음

## 구현 메모

- 모든 Agent는 `Agent` 프로토콜(`name`, `async run(payload) -> dict`)을 준수해야 한다.
- Agent 반환 타입이 `dict`가 아니면 타입 오류로 처리한다.
- 각 단계 결과는 추적 가능하도록 `steps`에 남긴다.
