# 인터페이스 정의서

## 1. 문서 개요

- 문서 목적: 외부 API, 내부 Agent contract, 서비스/저장소 인터페이스를 정의한다.
- 기준 범위: 현재 구현된 FastAPI 엔드포인트와 Agent/Provider/Repository 인터페이스

## 2. 외부 인터페이스

### 2.1 HTTP API

#### `GET /`

| 항목 | 내용 |
| --- | --- |
| 목적 | 서비스 메타 정보 확인 |
| 응답 | `service`, `docs`, `health` |

응답 예시:

```json
{
  "service": "finagent-sme",
  "docs": "/docs",
  "health": "/api/health"
}
```

#### `GET /api/health`

| 항목 | 내용 |
| --- | --- |
| 목적 | 헬스 체크 |
| 소비자 | 프론트엔드, 운영자 |

#### `POST /api/v1/workflows/orchestrator`

| 항목 | 내용 |
| --- | --- |
| 목적 | Supervisor 기반 신용 심사 워크플로우 실행 |
| 요청 Content-Type | `application/json` |
| 요청 헤더 | 선택적 `x-request-id` |
| 요청 바디 | `CreditAssessmentRequest` |

요청 스키마:

```json
{
  "company_name": "회사명"
}
```

정상 응답 스키마:

```json
{
  "request_id": "req-...",
  "company_name": "회사명",
  "status": "success | partial | failed | not_target",
  "decision": "...",
  "report": {},
  "steps": [],
  "context": {}
}
```

오류 응답 규약:

```json
{
  "code": "INVALID_INPUT | AGENT_EXECUTION_FAILED",
  "message": "오류 메시지",
  "detail": {},
  "request_id": "req-..."
}
```

#### `POST /api/v1/workflows/credit-assessment`

- `orchestrator` 엔드포인트의 호환 엔드포인트
- 요청/응답 계약은 동일하다

## 3. 입력/출력 데이터 계약

### 3.1 `CreditAssessmentRequest`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `company_name` | `string` | 예 | 심사 대상 기업명 |

검증 규칙:

- 최소 길이 `1`
- 공백만 입력된 경우 API 레벨에서 `400 INVALID_INPUT`

### 3.2 공통 Agent 출력 계약

모든 `Agent.run(payload)`는 아래 필드를 포함해야 한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `status` | `success | partial | failed | skipped` | 단계 상태 |
| `error_code` | `string` | 표준 에러 코드 |
| `fallback_used` | `boolean` | fallback 사용 여부 |
| `latency_ms` | `integer` | 실행 시간 |

### 3.3 최종 Workflow 상태값

| 값 | 의미 |
| --- | --- |
| `success` | 모든 필수 단계 성공 |
| `partial` | 일부 단계 실패 또는 fallback 사용 |
| `failed` | 필수 단계 실패 |
| `not_target` | 기업 마스터에 대상 기업 미존재 |

## 4. 내부 인터페이스

### 4.1 Agent 프로토콜

```python
class Agent(Protocol):
    name: str
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]: ...
```

설계 규칙:

- `name`은 Supervisor 그래프 노드 식별자다
- 반환값은 반드시 `dict`
- 비즈니스 데이터와 실행 메타데이터를 함께 반환한다

### 4.2 Provider 인터페이스

| Provider | 주요 메서드 | 목적 |
| --- | --- | --- |
| `FinancialDataProvider` | `get_financial_statements`, `calc_financial_ratios` | 재무 분석 도구 추상화 |
| `IndustryDataProvider` | `map_corp_to_ksic`, `get_macro_indicators` | 산업/거시 도구 추상화 |
| `NewsCollectionProvider` | `execute_news_pipeline` | 뉴스 수집/요약 파이프라인 추상화 |

### 4.3 Repository 인터페이스

| Repository | 함수 | 설명 |
| --- | --- | --- |
| `company_master` | `find_company_row_by_name` | 기업명 기준 단일 회사 조회 |
| `company_master` | `get_company_info_by_corp_code` | 기업 코드 기준 상세 정보 조회 |
| `financial_feature` | `get_financial_rows_by_corp_code` | 재무 피처 연도별 조회 |
| `company_registry` | `save_outputs_to_database` | 배치 산출물 저장 |

## 5. 데이터베이스 인터페이스

### 5.1 조회 테이블

| 테이블 | 주요 소비자 |
| --- | --- |
| `sme_list` | `CompanyResolverAgent`, 뉴스 수집 파이프라인 |
| `financial_features` | 재무 분석, 리스크 이벤트 재무 이상 탐지 |
| `daum_news_articles` | 뉴스 수집 적재 결과 |
| `financial_error_logs` | 배치 오류 로그 분석 |

### 5.2 키 설계

| 테이블 | 키 |
| --- | --- |
| `sme_list` | 실질 키 `corp_code` |
| `financial_features` | 복합 키 성격 `corp_code + stock_code + year` |
| `daum_news_articles` | 유니크 제약 `stock_code + url` |
| `financial_error_logs` | 복합 키 성격 `corp_code + error_type + message` |

## 6. 외부 연동 인터페이스

| 시스템 | 용도 | 사용 위치 |
| --- | --- | --- |
| OpenAI API | 뉴스 요약, 감성 분석, 판단 설명 생성 | `news.py`, `sentiment_analyzer.py`, `explanation_generator.py` |
| OpenDART | 기업/재무 데이터 수집 | company registry, 재무 분석 |
| 다음 뉴스 | 기사 수집 | `backend/tools/news.py` |
| ECOS/KOSIS | 거시/산업 지표 | 산업 분석 |
| Langfuse | trace/observation 수집 | `backend/common/langfuse.py` 중심 |

## 7. 에러 인터페이스

| 코드 | 설명 | HTTP 상태 |
| --- | --- | --- |
| `INVALID_INPUT` | 입력 검증 실패 | 400 |
| `COMPANY_NOT_FOUND` | 대상 기업 미존재 | 200 응답 본문 상태값 `not_target` |
| `AGENT_EXECUTION_FAILED` | 오케스트레이터 치명 오류 | 500 |
| `NEWS_PIPELINE_DEGRADED` | 뉴스 파이프라인 부분 실패 | workflow `partial` |
| `FINANCIAL_TOOL_FALLBACK` | 재무 도구 fallback 발생 | workflow `partial` |
| `INDUSTRY_TOOL_FALLBACK` | 산업 도구 fallback 발생 | workflow `partial` |
| `DECISION_DEGRADED` | 설명 생성 등 일부 판단 degraded | workflow `partial` |
