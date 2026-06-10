# 유스케이스 명세서

## 1. 문서 개요

- 시스템명: `FinAgent-SME`
- 목적: 현재 구현된 심사 요청, 데이터 구축, 결과 검증 흐름을 정의한다
- 기준 범위: `Streamlit -> FastAPI -> WorkflowOrchestrator -> Agent Graph -> Report/Validation`

## 2. 액터 정의

| 액터 | 설명 |
| --- | --- |
| 심사 담당자 | 회사명을 입력하고 심사 결과를 확인하는 사용자 |
| Streamlit UI | 검색/리포트 화면 |
| FastAPI API | HTTP 진입점, 입력 검증, 응답 매핑 |
| WorkflowOrchestrator | agent 실행 순서와 상태를 관리하는 supervisor |
| Agent | 개별 분석/판단/검증 담당 컴포넌트 |
| PostgreSQL | 기업 마스터, 기업개황, 재무, 뉴스 저장소 |
| 외부 API | OpenAI, OpenDART, ECOS, KOSIS, Daum News |
| Langfuse | trace, observation, score 저장 |

## 3. 핵심 유스케이스

| ID | 유스케이스명 | 주 액터 | 목표 |
| --- | --- | --- | --- |
| UC-01 | 기업 심사 요청 | 심사 담당자 | 회사명 기준 심사 워크플로우를 실행한다 |
| UC-02 | 대상 기업 판별 | WorkflowOrchestrator | 기업 마스터에서 심사 대상 기업인지 확인한다 |
| UC-03 | 분석 수행 | WorkflowOrchestrator | 뉴스/재무/산업/리스크 분석을 실행한다 |
| UC-04 | 심사 판단 생성 | DecisionAgent | 승인/검토/거절과 등급/한도를 산출한다 |
| UC-05 | 리포트 제공 | ReportAgent | 사람이 읽을 수 있는 결과 리포트를 만든다 |
| UC-06 | 결과 검증 기록 | ValidationAgent | 결과 정합성을 검증하고 score를 남긴다 |
| UC-07 | DB 구축 배치 실행 | 운영자 | 기업/재무 DB를 구축한다 |

## 4. 유스케이스 상세

### UC-01 기업 심사 요청

| 항목 | 내용 |
| --- | --- |
| 트리거 | 사용자가 검색 화면에서 회사명을 입력하고 `검색` 버튼을 누른다 |
| 선행조건 | 백엔드와 DB가 동작 중이며 기업 마스터가 적재돼 있다 |
| 후행조건 | `status`, `context`, `steps`, `request_id`를 포함한 응답을 받는다 |

기본 흐름:

1. 사용자가 회사명을 입력한다.
2. UI가 `POST /api/v1/workflows/orchestrator`를 호출한다.
3. API가 요청을 검증하고 `request_id`를 바인딩한다.
4. 워크플로우가 기업 판별을 수행한다.
5. 대상 기업이면 분석, 판단, 리포트, 검증을 수행한다.
6. 결과를 JSON으로 반환한다.

대체 흐름:

- 공백 회사명: `400 INVALID_INPUT`
- 대상 기업 미존재: `200 + status=not_target`
- 내부 예외: `500 AGENT_EXECUTION_FAILED`

### UC-02 대상 기업 판별

| 항목 | 내용 |
| --- | --- |
| 주체 | `CompanyResolverAgent` |
| 입력 | `company_name` |
| 출력 | `company_found`, `corp_code`, `corp_name`, `company_profile` |

규칙:

- `sme_list`를 우선 조회한다.
- `company_profiles`가 있으면 최신 개황 필드를 병합한다.
- 미존재는 예외가 아니라 정상적인 `not_target` 종료다.

### UC-03 분석 수행

| 항목 | 내용 |
| --- | --- |
| 주체 | `NewsCollectorAgent`, `FinancialAnalystAgent`, `RiskEventAgent`, `IndustryAnalystAgent` |
| 입력 | `company_name`, `corp_code`, `corp_name` |
| 출력 | 뉴스, 재무, 산업, 리스크 관련 context |

규칙:

- 시작 노드는 `news_collector`, `financial_analyst`
- `risk_event`는 뉴스 결과를 사용
- `industry_analyst`는 재무 비율을 사용
- fallback 발생 시 step 메타데이터에 반영

### UC-04 심사 판단 생성

| 항목 | 내용 |
| --- | --- |
| 주체 | `DecisionAgent` |
| 입력 | 재무/산업/리스크 context |
| 출력 | `decision`, `credit_grade`, `credit_score`, `recommended_limit`, `explanation` |

### UC-05 리포트 제공

| 항목 | 내용 |
| --- | --- |
| 주체 | `ReportAgent` |
| 입력 | decision 결과와 설명 |
| 출력 | `report` |

현재 리포트 핵심 필드:

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

### UC-06 결과 검증 기록

| 항목 | 내용 |
| --- | --- |
| 주체 | `ValidationAgent` |
| 입력 | `decision`, `credit_grade`, `recommended_limit`, `report` |
| 출력 | `validation_result` |

검증 항목 예시:

- `decision` 값 유효성
- `report.company_name` 정합성
- `report.summary`, `report.recommendation` 존재
- `decision=reject`면 `recommended_limit=0`

Langfuse 활성화 시 아래 score를 기록한다.

- `validation_pass_rate`
- `workflow_contract_valid`
- `failed_check_count`

### UC-07 DB 구축 배치 실행

| 항목 | 내용 |
| --- | --- |
| 주체 | `scripts/setup-db.sh build`, `execute_dart_pipeline()` |
| 입력 | `year`, `sample_size`, `skip_db_save` |
| 출력 | 적재 건수와 통계 |

현재 저장 대상:

- `sme_list`
- `company_profiles`
- `financial_features`
- `financial_error_logs`

## 5. 비기능 요구사항

| 구분 | 요구사항 |
| --- | --- |
| 추적성 | `request_id`와 로그로 요청 단위 추적이 가능해야 한다 |
| 확장성 | agent 노드를 그래프에 추가할 수 있어야 한다 |
| 신뢰성 | fallback과 실패를 `steps`에 남겨야 한다 |
| 보안 | 민감정보를 로그에 남기지 않는다 |

## 6. 현재 한계

- 공개 API는 `company_name`만 받는다
- UI에서 base URL 수정 기능이 없다
- 문서 업로드/PDF 분석은 공개 UI/API로 아직 노출되지 않았다
