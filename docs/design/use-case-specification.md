# 유스케이스 명세서

## 1. 문서 개요

- 시스템명: `FinAgent-SME`
- 문서 목적: 중소기업 대출 심사 워크플로우의 사용자 목표, 입력 조건, 정상/예외 흐름을 명확히 정의한다.
- 대상 독자: 금융기관 심사 담당자, 백엔드/프론트엔드 개발자, 평가자
- 기준 범위: `Frontend -> Supervisor(WorkflowOrchestrator) -> Sub-Agent -> 최종 리포트`

## 2. 액터 정의

| 액터 | 설명 |
| --- | --- |
| 심사 담당자 | 회사명을 입력하고 심사 결과와 리포트를 확인하는 최종 사용자 |
| 프론트엔드 UI | Streamlit 기반 검색/리포트 화면 |
| Supervisor | `WorkflowOrchestrator`, 전체 멀티에이전트 흐름 제어 |
| Sub-Agent | 기업 판별, 뉴스 수집, 재무 분석, 산업 분석, 리스크 분석, 판단, 리포트 생성 담당 |
| 외부 데이터 소스 | OpenDART, ECOS, KOSIS, 다음 뉴스, OpenAI API |
| PostgreSQL | 기업 마스터, 재무 피처, 뉴스 적재 저장소 |

## 3. 핵심 유스케이스 목록

| ID | 유스케이스명 | 주 액터 | 목표 |
| --- | --- | --- | --- |
| UC-01 | 기업 심사 요청 | 심사 담당자 | 회사명 기준으로 심사 워크플로우를 실행한다 |
| UC-02 | 대상 기업 여부 판별 | Supervisor | 기업 마스터에서 심사 대상 기업인지 확인한다 |
| UC-03 | 병렬 분석 수행 | Supervisor | 뉴스, 재무, 산업, 리스크, 문서 분석을 분산 수행한다 |
| UC-04 | 심사 판단 생성 | Supervisor | 분석 결과를 종합해 승인/검토/거절을 산출한다 |
| UC-05 | 최종 리포트 제공 | 심사 담당자 | 심사 근거와 권고안을 읽을 수 있는 리포트를 확인한다 |
| UC-06 | 데이터 구축 배치 실행 | 운영자/개발자 | 기업 마스터 및 재무 피처 DB를 구축한다 |

## 4. 유스케이스 상세

### UC-01 기업 심사 요청

| 항목 | 내용 |
| --- | --- |
| 목적 | 심사 대상 회사에 대한 자동 심사 워크플로우를 실행한다 |
| 트리거 | 사용자가 검색 화면에서 회사명을 입력하고 `검색` 버튼을 누른다 |
| 선행조건 | 백엔드 API, PostgreSQL, 기업 마스터 데이터가 준비되어 있다 |
| 후행조건 | 심사 결과 또는 오류 응답이 사용자에게 전달된다 |

#### 기본 흐름

1. 사용자가 회사명을 입력한다.
2. 프론트엔드가 `POST /api/v1/workflows/orchestrator`를 호출한다.
3. API는 요청 유효성을 검사하고 `request_id`를 바인딩한다.
4. Supervisor가 기업 판별 에이전트를 실행한다.
5. 대상 기업이면 병렬 분석 Sub-Agent를 실행한다.
6. Supervisor가 분석 결과를 병합한다.
7. Decision Agent가 신용등급, 승인 여부, 추천 한도를 계산한다.
8. Report Agent가 최종 리포트를 생성한다.
9. API가 `status`, `decision`, `report`, `steps`, `context`를 반환한다.

#### 대체 흐름

| 분기 | 처리 |
| --- | --- |
| 회사명 공백 | `400 INVALID_INPUT` 반환 |
| 대상 기업 미존재 | `not_target` 상태로 정상 종료 |
| 일부 Agent 실패 + fallback 가능 | `partial` 상태로 결과 지속 반환 |
| 치명적 실패 | `500 AGENT_EXECUTION_FAILED` 반환 |

### UC-02 대상 기업 여부 판별

| 항목 | 내용 |
| --- | --- |
| 목적 | 회사명이 심사 대상 기업 마스터에 존재하는지 확인한다 |
| 주체 | `CompanyResolverAgent` |
| 입력 | `company_name` |
| 출력 | `company_found`, `corp_code`, `corp_name` 또는 `not_target` |

#### 규칙

- 회사명이 비어 있으면 예외 처리한다.
- 기업 마스터 `sme_list`에서 가장 최근 데이터를 우선 조회한다.
- 미존재 시 예외가 아니라 정상적인 `not_target` 종료로 간주한다.

### UC-03 병렬 분석 수행

| 항목 | 내용 |
| --- | --- |
| 목적 | 기업 리스크 심사에 필요한 다각도 분석을 동시 수행한다 |
| 주체 | Supervisor, `NewsCollectorAgent`, `FinancialAnalystAgent`, `IndustryAnalystAgent`, `RiskEventAgent`, `MultiModalDocumentAgent(optional)` |
| 입력 | `corp_code`, `corp_name`, `company_name`, 선택적 `pdf_path` |
| 출력 | 뉴스, 재무, 산업, 리스크, 문서 컨텍스트 |

#### 처리 규칙

- 뉴스 수집과 재무 분석은 병렬 시작 노드로 수행한다.
- `RiskEventAgent`는 `news_data`를 입력으로 활용한다.
- `IndustryAnalystAgent`는 `financial_ratios`를 입력으로 활용한다.
- 문서 파일이 없으면 문서 분석은 생략 또는 선택 미실행이다.
- 일부 도구 실패 시 fallback 결과와 `tool_errors`를 남긴다.

### UC-04 심사 판단 생성

| 항목 | 내용 |
| --- | --- |
| 목적 | 병합된 분석 결과를 기반으로 승인 여부와 등급을 계산한다 |
| 주체 | `DecisionAgent` |
| 입력 | `overall_risk_level`, 재무 요약, 산업 비교, 문서 리스크, `grade_cap` |
| 출력 | `decision`, `credit_grade`, `credit_score`, `recommended_limit`, `explanation` |

#### 판단 기준 요약

- 리스크 이벤트 수와 심각도에 따라 감점한다.
- 재무지표 이상, 적자, 고부채 등은 거절 또는 등급 하향 사유가 된다.
- `grade_cap`이 존재하면 최종 등급 상한을 제한한다.
- 설명 생성 실패 시 규칙 기반 문구로 fallback 한다.

### UC-05 최종 리포트 제공

| 항목 | 내용 |
| --- | --- |
| 목적 | 최종 심사 판단을 사람이 읽기 쉬운 리포트로 제공한다 |
| 주체 | `ReportAgent` |
| 입력 | Decision 결과, 판단 근거, 리스크 요약 |
| 출력 | `report.summary`, `key_risks`, `recommendation` |

#### 품질 규칙

- 설명 생성 결과가 없으면 fallback summary/recommendation을 생성한다.
- 리포트는 `company_name`, `corp_code`, `decision`, `credit_grade`, `recommended_limit`를 포함해야 한다.

### UC-06 데이터 구축 배치 실행

| 항목 | 내용 |
| --- | --- |
| 목적 | 심사 대상 기업 마스터와 재무 피처를 DART 기반으로 구축한다 |
| 주체 | 운영자, `company_registry` 파이프라인 |
| 입력 | `year`, `sample_size`, API key |
| 출력 | `sme_list`, `financial_features`, `financial_error_logs` 테이블 적재 |

#### 기본 흐름

1. 운영자가 DB를 기동한다.
2. 배치 파이프라인이 중소기업 후보를 로드한다.
3. 기업별 DART 수집과 전처리를 수행한다.
4. 기업 마스터/재무 피처/오류 로그 DataFrame을 생성한다.
5. 신규 행만 PostgreSQL에 저장한다.

## 5. 비기능 요구사항

| 구분 | 요구사항 |
| --- | --- |
| 성능 | 병렬 Agent 실행으로 심사 대기 시간을 단축해야 한다 |
| 신뢰성 | Agent/Tool 실패 시 `partial`, `fallback_used`, `error_code`를 남겨야 한다 |
| 추적성 | `request_id`와 Langfuse trace로 요청 단위 추적이 가능해야 한다 |
| 보안 | 민감정보를 로그와 trace metadata에 직접 기록하지 않는다 |
| 확장성 | 새로운 Agent를 Supervisor 그래프에 노드 단위로 추가할 수 있어야 한다 |

## 6. 산출물

- API 응답 JSON
- 단계별 `steps`
- 최종 `report`
- 운영 로그
- Langfuse trace
