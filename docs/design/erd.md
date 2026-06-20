# ERD

## 1. 문서 개요

- 목적: 현재 코드가 직접 읽거나 쓰는 핵심 테이블을 설명한다
- 범위: PostgreSQL 기준 논리 모델

## 2. 엔터티 관계도

```mermaid
erDiagram
    SME_LIST ||--o| COMPANY_PROFILES : enriches
    SME_LIST ||--o{ FINANCIAL_FEATURES : has
    SME_LIST ||--o{ DAUM_NEWS_ARTICLES : collects
    SME_LIST ||--o{ FINANCIAL_ERROR_LOGS : may_log

    SME_LIST {
        string corp_code PK
        string corp_name
        string stock_code
        float avg_revenue_last_3y
        float total_assets
        datetime created_at
    }

    COMPANY_PROFILES {
        string corp_code PK
        string corp_name
        string stock_code
        string ceo_name
        string homepage_url
        string industry_code
        datetime created_at
    }

    FINANCIAL_FEATURES {
        string corp_code
        string corp_name
        string stock_code
        int year
        float revenue
        float operating_income
        float net_income
        float total_assets
        float total_liabilities
        float total_equity
        datetime created_at
    }

    DAUM_NEWS_ARTICLES {
        int id PK
        string stock_code
        string corp_name
        string news_title
        string press_name
        datetime published_at
        string url
        string content
        string content_type
        datetime created_at
    }

    FINANCIAL_ERROR_LOGS {
        string corp_code
        string error_type
        string message
        datetime created_at
    }

    WORKFLOW_JOBS {
        string job_id PK
        string request_id
        string company_name
        string status
        text result_json
        text step_summary_json
        string error_code
        string error_message
        datetime submitted_at
        datetime started_at
        datetime finished_at
        datetime updated_at
    }
```

`workflow_jobs`는 기업 master와 외래키로 묶이지 않는 실행 이력입니다. 입력 당시 회사명과 추적 ID를 보존하고, 완료된 workflow payload를 JSON 문자열로 저장합니다.

## 3. 테이블 설명

### `sme_list`

- 기업 마스터
- `CompanyResolverAgent`의 기본 조회 대상
- 뉴스 수집 대상 기업 목록의 기준

핵심 컬럼:

- `corp_code`
- `corp_name`
- `stock_code`
- `avg_revenue_last_3y`
- `total_assets`
- `created_at`

### `company_profiles`

- 기업개황 보강 테이블
- `sme_list`와 같은 `corp_code`를 기준으로 최신 개황 정보를 병합

대표 컬럼:

- `corp_code`
- `corp_name`
- `stock_code`
- `ceo_name`
- `address`
- `homepage_url`
- `ir_url`
- `phone_number`
- `industry_code`
- `created_at`

### `financial_features`

- 재무 분석용 연도별 피처 저장소
- `FinancialAnalystAgent`와 일부 리스크 분석에서 사용

대표 키 성격:

- `corp_code + stock_code + year`

### `daum_news_articles`

- 뉴스 수집 적재 테이블
- ORM 모델에서 `(stock_code, url)` 유니크 제약을 사용

대표 컬럼:

- `stock_code`
- `corp_name`
- `news_title`
- `press_name`
- `published_at`
- `url`
- `content`
- `content_type`
- `created_at`

### `financial_error_logs`

- DB 구축 파이프라인 실패 이력 저장

키 성격:

- `corp_code + error_type + message`

### `workflow_jobs`

- 비동기 심사 job의 queue와 결과 저장소
- repository가 최초 접근 시 `CREATE TABLE IF NOT EXISTS`로 생성
- `job_id`가 기본 키이며 `request_id`로 로그·Langfuse trace와 연결
- `result_json`, `step_summary_json`은 성공 완료 시 기록
- 서버 재시작 시 미완료 job은 `failed / WORKER_RESTARTED`로 전이

상태 전이:

```mermaid
stateDiagram-v2
    [*] --> queued: submit
    queued --> running: worker claim
    running --> succeeded: result saved
    running --> failed: timeout / exception
    queued --> failed: server restart recovery
    running --> failed: server restart recovery
    succeeded --> [*]
    failed --> [*]
```

## 4. 논리 관계

| From | To | 관계 | 설명 |
| --- | --- | --- | --- |
| `sme_list` | `company_profiles` | 1:0..1 | 기업개황 보강 |
| `sme_list` | `financial_features` | 1:N | 연도별 재무 피처 |
| `sme_list` | `daum_news_articles` | 1:N | 수집된 뉴스 기사 |
| `sme_list` | `financial_error_logs` | 1:N | 배치 오류 로그 |

`workflow_jobs`와 업무 테이블 사이에는 현재 물리적 외래키가 없습니다.

## 5. 사용 시나리오

| 시나리오 | 읽기/쓰기 |
| --- | --- |
| 대상 기업 판별 | `sme_list` 읽기, `company_profiles` 읽기 |
| 재무 분석 | `financial_features` 읽기 |
| 뉴스 수집 | `sme_list` 읽기, `daum_news_articles` 쓰기 |
| DB 구축 | `sme_list`, `company_profiles`, `financial_features`, `financial_error_logs` 쓰기 |
| 비동기 심사 | `workflow_jobs` 생성, claim, 상태/결과 갱신 |

## 6. 설계 메모

- 일부 키/제약은 코드 레벨에서 관리된다
- 신규 컬럼은 저장 시 nullable TEXT 컬럼으로 자동 추가될 수 있다
- `workflow_jobs`는 현재 운영 queue와 실행 결과를 함께 보관한다
- agent별 정규화 실행 테이블(`agent_runs`)은 아직 도입되지 않았다
- 산업 방법론 벡터는 PostgreSQL이 아니라 `backend/vectorstore/industry_knowledge/`의 Chroma에 저장된다
