# 인터페이스 정의서

## 1. 문서 개요

- 목적: 현재 공개 API와 내부 주요 contract를 정리한다
- 범위: FastAPI 엔드포인트, agent contract, repository/service 경계

## 2. 외부 HTTP 인터페이스

### `GET /`

응답:

```json
{
  "service": "finagent-sme",
  "docs": "/docs",
  "health": "/api/health"
}
```

### `GET /api/health`

응답:

```json
{
  "status": "ok"
}
```

### `POST /api/v1/workflows/orchestrator`

### `POST /api/v1/workflows/credit-assessment`

두 엔드포인트는 현재 동일한 워크플로우를 즉시 실행한다.

### `POST /api/v1/workflows/jobs`

현재 프론트엔드 기본 진입점이다. 요청을 즉시 완료하지 않고 workflow job을 등록한다.

요청 바디:

```json
{
  "company_name": "회사명"
}
```

현재 공개 요청 모델:

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `company_name` | `string` | 예 | 심사 대상 기업명 |

검증:

- 최소 길이 `1`
- 공백만 입력된 경우 워크플로우 진입 직전 `400 INVALID_INPUT`

job 생성 응답 예시 (`202 Accepted`):

```json
{
  "job_id": "job-...",
  "request_id": "req-...",
  "company_name": "회사명",
  "status": "queued",
  "submitted_at": "2026-06-13T00:00:00+00:00",
  "status_url": "/api/v1/workflows/jobs/job-...",
  "result_url": "/api/v1/workflows/jobs/job-.../result"
}
```

### `GET /api/v1/workflows/jobs/{job_id}`

job 상태 응답 예시:

```json
{
  "job_id": "job-...",
  "request_id": "req-...",
  "company_name": "회사명",
  "status": "running",
  "submitted_at": "2026-06-13T00:00:00+00:00",
  "started_at": "2026-06-13T00:00:01+00:00",
  "finished_at": null,
  "error_code": null,
  "error_message": null,
  "step_summary": null
}
```

### `GET /api/v1/workflows/jobs/{job_id}/result`

성공적으로 완료된 job의 결과 응답 예시:

```json
{
  "request_id": "req-...",
  "company_name": "회사명",
  "status": "success",
  "context": {
    "decision": "approve",
    "credit_grade": "A",
    "report": {}
  },
  "steps": []
}
```

주의:

- job이 아직 끝나지 않으면 `409 JOB_NOT_COMPLETED`
- job이 실패했으면 `409 JOB_FAILED`
- 완료된 job만 최종 workflow 결과를 반환

### 동기 호환 엔드포인트 응답

`POST /api/v1/workflows/orchestrator`, `POST /api/v1/workflows/credit-assessment`는 아래 workflow 응답을 즉시 반환한다.

`not_target` 응답 예시:

```json
{
  "request_id": "req-...",
  "company_name": "회사명",
  "status": "not_target",
  "code": "COMPANY_NOT_FOUND",
  "message": "대상 기업이 아닙니다.",
  "context": {},
  "steps": []
}
```

오류 응답 예시:

```json
{
  "code": "AGENT_EXECUTION_FAILED",
  "message": "오케스트레이터 실행 중 오류가 발생했습니다.",
  "detail": {
    "company_name": "회사명"
  },
  "request_id": "req-..."
}
```

## 3. Workflow 응답 계약

### 상위 필드

| 필드 | 설명 |
| --- | --- |
| `request_id` | 요청 추적 ID |
| `company_name` | 정규화된 요청 기업명 |
| `status` | `success`, `partial`, `failed`, `not_target` |
| `context` | 누적 비즈니스 결과 |
| `steps` | step 실행 메타데이터 목록 |

### Job 상태 응답 상위 필드

| 필드 | 설명 |
| --- | --- |
| `job_id` | 비동기 workflow job ID |
| `request_id` | 요청 추적 ID |
| `company_name` | 정규화된 요청 기업명 |
| `status` | `queued`, `running`, `succeeded`, `failed` |
| `submitted_at` | 접수 시각 |
| `started_at` | 실행 시작 시각 |
| `finished_at` | 종료 시각 |
| `error_code` | 실패 코드 |
| `error_message` | 실패 메시지 |
| `step_summary` | 완료 시 step 결과 요약 |

### `steps[*]`

| 필드 | 설명 |
| --- | --- |
| `agent_name` | agent 식별자 |
| `ok` | downstream 전달 가능 여부 |
| `status` | agent 자체 상태 |
| `error_code` | 표준/도메인 코드 |
| `fallback_used` | fallback 사용 여부 |
| `latency_ms` | 실행 시간 |
| `output` | 해당 step의 비즈니스 출력 |
| `error` | 실패 문자열, 없으면 `null` |

## 4. 내부 Agent 인터페이스

```python
class Agent(Protocol):
    name: str
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]: ...
```

규칙:

- 반환값은 반드시 `dict`
- 공통 메타데이터는 `build_agent_output()` 사용 권장
- 비즈니스 데이터와 실행 메타데이터가 함께 반환될 수 있다

## 5. 내부 Provider 인터페이스

현재 주요 provider 추상화:

| Provider | 목적 |
| --- | --- |
| `FinancialDataProvider` | 재무 데이터 수집/계산 |
| `IndustryDataProvider` | KSIC/산업/거시 분석 |
| `NewsCollectionProvider` | 뉴스 수집 파이프라인 |

## 6. Repository / Service 인터페이스

대표 함수:

| 계층 | 함수 | 설명 |
| --- | --- | --- |
| Repository | `find_company_row_by_name` | 기업명 기준 단건 조회 |
| Repository | `get_company_info_by_corp_code` | 기업 코드 기준 조회 |
| Repository | `save_outputs_to_database` | DB 구축 산출물 저장 |
| Service | `find_company_by_name` | 기업개황 포함 조회 |
| Service | `execute_dart_pipeline` | DART 기반 DB 구축 |

## 7. 데이터베이스 인터페이스

현재 주요 테이블:

- `sme_list`
- `company_profiles`
- `financial_features`
- `financial_error_logs`
- `daum_news_articles`

## 8. 외부 연동

| 시스템 | 사용 위치 |
| --- | --- |
| OpenRouter API | 뉴스 요약, 판단 설명, 일부 분석 |
| OpenDART | 기업/재무 데이터 수집 |
| ECOS | 거시 지표 조회 |
| KOSIS | 업황 지표 조회 |
| Daum News | 기사 목록/본문 수집 |
| Langfuse | trace/observation/score |

## 9. 현재 비공개 확장 포인트

코드 레벨에서는 아래 값들이 존재하지만, 공개 HTTP 요청 모델에는 포함되지 않는다.

- `pdf_path`
- `continue_on_error`
- `target_year`
- agent별 timeout/retry override 필드
