# FinAgent-SME

FinAgent-SME는 중소기업 대상 B2B 거래 리스크 심사를 지원하는 멀티 에이전트 시스템입니다. 현재 저장소는 FastAPI 백엔드, Streamlit 프론트엔드, PostgreSQL 기반 기업/재무 데이터 저장소, LangGraph 오케스트레이터를 포함합니다.

## 현재 구현 상태

- 기본 심사 진입점: `POST /api/v1/workflows/jobs`
- 결과 조회 방식: `job submit -> status poll -> result fetch`
- 호환용 동기 엔드포인트: `POST /api/v1/workflows/orchestrator`, `POST /api/v1/workflows/credit-assessment`
- 기본 UI: Streamlit 검색/리포트 화면
- 오케스트레이터 흐름:
  1. `CompanyResolverAgent`
  2. 시작 분석 노드: `NewsCollectorAgent`, `FinancialAnalystAgent`
  3. 의존 분석 노드: `RiskEventAgent`(`news_collector` 이후), `IndustryAnalystAgent`(`financial_analyst` 이후)
  4. 후속 단계: `DecisionAgent` -> `ReportAgent` -> `ValidationAgent`
- 선택 기능: 내부 워크플로우 payload에 `pdf_path`가 있을 때 `MultiModalDocumentAgent` 추가 가능
- 관측성: `request_id` 기반 구조화 로그, Langfuse trace/score 연동 지원
- 실행 모델: FastAPI 앱 시작 시 background job runner가 queued job을 처리

현재 공개 HTTP API 스키마는 `company_name`만 받습니다. `pdf_path`, `continue_on_error` 같은 옵션은 코드 레벨 확장 포인트로는 존재하지만, 공개 요청 스키마에는 아직 노출되지 않았습니다.

## 저장소 구조

```text
FinAgent-SME/
├── backend/     # FastAPI, agent, orchestrator, data/integration 계층
├── frontend/    # Streamlit UI
├── docs/        # 설계/규칙 문서
├── scripts/     # 로컬 실행/세팅 스크립트
├── tests/       # pytest 및 수동 검증 자료
└── requirements.txt
```

## 핵심 디렉터리

- `backend/common`: env, settings, logging, 공통 contract/provider/tool runtime
- `backend/agents`: 개별 agent와 orchestrator
- `backend/data`: DB 연결, repository, service
- `backend/integrations`: DART/ECOS/KOSIS 클라이언트
- `backend/tools`: 재무/산업/뉴스/기업구축 로직
- `frontend/views`: 검색/리포트 화면

## 요구사항

- Python `3.13+`
- Docker Desktop 또는 `docker compose` (로컬 PostgreSQL 사용 시)
- 선택적 외부 키:
  - `OPEN_ROUTER_API_KEY`
  - `OPEN_DART_API_KEY`
  - `ECOS_API_KEY`
  - `KOSIS_API_KEY`
  - `LANGFUSE_PUBLIC_KEY`
  - `LANGFUSE_SECRET_KEY`

LLM 호출은 기본적으로 OpenRouter 설정을 사용합니다. `OPEN_AI_API_KEY`, `OPENAI_API_KEY`, `OPEN_API_KEY`는 레거시 호환용 fallback이며 신규 설정에는 권장하지 않습니다.

현재 프론트엔드는 Node.js 빌드 없이 Streamlit으로 실행됩니다.

## 환경 변수

프로젝트는 주로 `backend/.env`를 읽습니다. 예시 파일은 저장소에 포함되어 있지 않으므로 직접 생성해야 합니다.

```env
OPEN_ROUTER_API_KEY=...
OPEN_ROUTER_BASE_URL=https://openrouter.ai/api/v1
OPEN_ROUTER_MODEL=openai/gpt-4o-mini
OPEN_DART_API_KEY=...
ECOS_API_KEY=...
KOSIS_API_KEY=...
DATABASE_URL=postgresql+psycopg2://finagent:finagent@localhost:5432/finagent

# DATABASE_URL 대신 아래 조합도 사용 가능
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=finagent
POSTGRES_PASSWORD=finagent
POSTGRES_DB=finagent

LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development

# 레거시 호환 변수 (신규 설정 비권장)
# OPEN_AI_API_KEY=...
# OPENAI_API_KEY=...
# OPEN_API_KEY=...
```

## 실행 방법

모든 명령은 프로젝트 루트에서 실행합니다.

### 1. 가상환경과 의존성 설치

```bash
./scripts/setup-env.sh
```

### 2. PostgreSQL 실행

```bash
./scripts/setup-db.sh up
./scripts/setup-db.sh status
./scripts/setup-db.sh logs
```

중지:

```bash
./scripts/setup-db.sh down
```

### 3. 기업/재무 데이터 적재

```bash
./scripts/setup-db.sh build --year 2024 --sample-size 10
```

이 파이프라인은 `sme_list`, `company_profiles`, `financial_features`, `financial_error_logs`를 생성하거나 갱신합니다.

### 4. 백엔드와 프론트 실행

```bash
./scripts/run-server.sh up
./scripts/run-server.sh status
./scripts/run-server.sh logs
```

중지:

```bash
./scripts/run-server.sh down
```

### 5. 전체 스택 한 번에 실행

```bash
./scripts/run-all.sh up
./scripts/run-all.sh status
./scripts/run-all.sh logs
./scripts/run-all.sh down
```

### 6. 개별 개발 실행

```bash
./scripts/setup-env.sh
./scripts/setup-db.sh up
./.venv/bin/python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
cd frontend
../.venv/bin/python -m streamlit run main.py --server.address 0.0.0.0 --server.port 8501
```

## 접속 주소

- Backend: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Frontend: `http://localhost:8501`

## API 요약

### `GET /`

```json
{
  "service": "finagent-sme",
  "docs": "/docs",
  "health": "/api/health"
}
```

### `GET /api/health`

```json
{
  "status": "ok"
}
```

### `POST /api/v1/workflows/jobs`

요청:

```json
{
  "company_name": "테스트기업"
}
```

응답 예시 (`202 Accepted`):

```json
{
  "job_id": "job-123456789abc",
  "request_id": "req-123456789abc",
  "company_name": "테스트기업",
  "status": "queued",
  "submitted_at": "2026-06-13T00:00:00+00:00",
  "status_url": "/api/v1/workflows/jobs/job-123456789abc",
  "result_url": "/api/v1/workflows/jobs/job-123456789abc/result"
}
```

### `GET /api/v1/workflows/jobs/{job_id}`

응답 예시:

```json
{
  "job_id": "job-123456789abc",
  "request_id": "req-123456789abc",
  "company_name": "테스트기업",
  "status": "running",
  "submitted_at": "2026-06-13T00:00:00+00:00",
  "started_at": "2026-06-13T00:00:01+00:00",
  "finished_at": null,
  "error_code": null,
  "error_message": null,
  "step_summary": null
}
```

`status`는 `queued`, `running`, `succeeded`, `failed` 중 하나입니다.

### `GET /api/v1/workflows/jobs/{job_id}/result`

완료된 job의 최종 결과는 아래처럼 반환됩니다.

```json
{
  "request_id": "req-123456789abc",
  "company_name": "테스트기업",
  "status": "success",
  "context": {
    "corp_code": "00123456",
    "corp_name": "테스트기업",
    "decision": "approve",
    "credit_grade": "A",
    "report": {}
  },
  "steps": []
}
```

`decision`, `credit_grade`, `report`, `validation_result` 같은 최종 산출물은 현재 `context` 내부에 들어갑니다.

`not_target` 예시:

```json
{
  "request_id": "req-123456789abc",
  "company_name": "없는기업",
  "status": "not_target",
  "code": "COMPANY_NOT_FOUND",
  "message": "대상 기업이 아닙니다.",
  "context": {
    "company_found": false,
    "workflow_code": "COMPANY_NOT_FOUND"
  },
  "steps": []
}
```

### 호환용 동기 실행 엔드포인트

- `POST /api/v1/workflows/orchestrator`
- `POST /api/v1/workflows/credit-assessment`

두 엔드포인트는 현재도 동일한 워크플로우를 즉시 실행하지만, 프론트엔드 기본 흐름과 운영 권장 경로는 `/jobs` 기반 비동기 구조입니다.

오류 응답 예시:

```json
{
  "code": "INVALID_INPUT",
  "message": "입력값이 올바르지 않습니다.",
  "detail": {
    "company_name": "   "
  },
  "request_id": "req-123456789abc"
}
```

## 테스트와 품질 확인

```bash
./tests/run_all_tests.sh
.venv/bin/pytest -o cache_dir=.cache/pytest tests/
.venv/bin/ruff check backend frontend tests
```

`frontend/`는 현재 Python Streamlit 앱이므로 `npm run lint` 대상이 아닙니다.

## 관련 문서

- [워크플로우](docs/domain/workflows.md)
- [유스케이스 명세](docs/design/use-case-specification.md)
- [컴포넌트 설계](docs/design/component-design.md)
- [인터페이스 정의](docs/design/interface-definition.md)
- [시퀀스 다이어그램](docs/design/sequence-diagram.md)
- [ERD](docs/design/erd.md)
