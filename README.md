# FinAgent-SME

FinAgent-SME는 중소기업 대상 B2B 거래 리스크 심사를 지원하는 멀티 에이전트 시스템입니다. 현재 저장소는 FastAPI 백엔드, Streamlit 프론트엔드, PostgreSQL 기반 기업/재무 데이터 저장소, LangGraph 오케스트레이터를 포함합니다.

> 회사명 하나로 기업 식별, 재무·산업·뉴스·리스크 분석, 신용 판단, 리포트 생성과 결과 검증까지 연결합니다.

## 한눈에 보기

```mermaid
flowchart LR
    U[심사 담당자] --> UI[Streamlit]
    UI -->|job 등록·조회| API[FastAPI]
    API --> Q[(workflow_jobs)]
    Q --> W[Background Job Runner]
    W --> G[LangGraph Agent Graph]
    G --> P[(PostgreSQL)]
    G --> V[(Chroma\n산업 방법론)]
    G --> E[OpenDART · ECOS · KOSIS\nDaum News · OpenRouter]
    G --> O[구조화 로그 · Langfuse]
    G --> R[판단 · 등급 · 한도 · 리포트]
    R --> Q
    Q --> UI
```

| 영역 | 현재 구현 |
| --- | --- |
| 사용자 경험 | 회사명 검색, SSE 진행 로그, polling fallback, 심사 리포트와 그래프, JSON 다운로드 |
| 실행 방식 | DB-backed 비동기 job + FastAPI 프로세스 내 단일 background runner |
| 분석 | 기업, 뉴스, 재무, 산업 방법론 RAG, 거시환경, 리스크 이벤트 |
| 결과 | 승인 판단, 신용등급, 추천한도, 근거, 최종 보고서, 계약 검증 |
| 품질 추적 | agent step metadata, `request_id` 로그, Langfuse trace/score, RAGAS 평가 |

## 에이전트 그래프

```mermaid
flowchart LR
    A[Company Resolver] --> B{대상 기업?}
    B -->|아니오| X[not_target]
    B -->|예| N[News Collector]
    B -->|예| F[Financial Analyst]
    B -.->|pdf_path가 있을 때| M[MultiModal Document]
    N --> K[Risk Event]
    F --> I[Industry Analyst\n산업 방법론 RAG]
    K --> D[Decision]
    I --> D
    F --> D
    M --> D
    D --> R[Report]
    R --> V[Validation]
    V -->|통과| Z[최종 context + steps]
    V -->|첫 실패| R
    V -->|재시도 소진| Y[VALIDATION_FAILED\n판단·보고서 차단]
```

## 문서 바로가기

| 목적 | 문서 |
| --- | --- |
| 전체 문서 지도 | [문서 허브](docs/README.md) |
| 신용 심사 흐름 | [워크플로우](docs/domain/workflows.md) |
| 시스템 구성 | [컴포넌트 설계](docs/design/component-design.md) |
| API 계약 | [인터페이스 정의](docs/design/interface-definition.md) |
| 데이터 모델 | [ERD](docs/design/erd.md) |
| 산업 RAG 적재·평가 | [산업 방법론 RAG](docs/rag/industry-methodology.md) |
| 개발 규칙 | [네이밍](docs/conventions/naming.md) · [에러 처리](docs/conventions/error-handling.md) · [테스트](docs/conventions/testing.md) |

## 현재 구현 상태

- 기본 심사 진입점: `POST /api/v1/workflows/jobs`
- 결과 조회 방식: `job submit -> SSE status stream -> polling fallback -> result fetch`
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
├── requirements.txt      # runtime 의존성
└── requirements-dev.txt  # 개발용 추가 의존성 (`./scripts/setup-env.sh`가 기본 사용)
```

## 핵심 디렉터리

- `backend/common`: env, settings, logging, 공통 contract/provider/tool runtime
- `backend/agents`: 개별 agent와 orchestrator
- `backend/data`: DB 연결, repository, service
- `backend/integrations`: DART/ECOS/KOSIS 클라이언트
- `backend/rag`: 산업 신용평가방법론 적재, 검색, RAGAS 평가
- `backend/tools`: 재무/산업/뉴스/기업구축 로직
- `frontend/views`: 검색/리포트 화면

## 요구사항

- Python `3.13+`
- Docker Desktop 또는 `docker compose` (컨테이너 실행 시)
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

Python 실행/검증 명령은 모두 `.venv/bin/...` 기준으로 통일합니다.

### 1. 가상환경과 의존성 설치

```bash
./scripts/setup-env.sh
```

기본값은 개발용 설치입니다. 배포 런타임만 맞추고 싶으면 아래처럼 실행할 수 있습니다.

```bash
./scripts/setup-env.sh --runtime
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

이 파이프라인은 `sme_list`, `company_profiles`, `financial_features`,
`financial_statement_details`, `financial_error_logs`를 생성하거나 갱신합니다.

산업 방법론 PDF를 Chroma에 적재하려면 다음 명령을 실행합니다. 최초 실행 시 한국어 임베딩 모델을 내려받을 수 있습니다.

```bash
.venv/bin/python -m backend.rag.ingest_industry_docs
```

### 4. Industry RAG MCP 서버 실행

산업 방법론 RAG 검색기는 MCP tool로도 노출됩니다. MCP client는
`lookup_industry_methodology` tool을 `list_tools`로 발견하고 `call_tool`로 호출할 수 있습니다.

```bash
.venv/bin/python -m backend.mcp.industry_server
```

### 5. 백엔드와 프론트 실행

```bash
./scripts/run-server.sh up
./scripts/run-server.sh status
./scripts/run-server.sh logs
```

중지:

```bash
./scripts/run-server.sh down
```

### 6. 전체 스택 한 번에 실행

```bash
./scripts/run-all.sh up
./scripts/run-all.sh status
./scripts/run-all.sh logs
./scripts/run-all.sh down
```

Docker Compose로 PostgreSQL, backend, frontend를 함께 실행할 수도 있습니다.
`backend/.env`를 준비한 뒤 프로젝트 루트에서 실행합니다.

```bash
docker compose -f backend/docker-compose.yml up --build -d
docker compose -f backend/docker-compose.yml ps
docker compose -f backend/docker-compose.yml logs -f backend frontend
docker compose -f backend/docker-compose.yml down
```

Compose 내부에서는 frontend가 `FINAGENT_BACKEND_URL=http://backend:8000`으로
backend를 호출합니다. 호스트 공개 포트는 `BACKEND_PORT`, `FRONTEND_PORT`,
`POSTGRES_PORT` 환경 변수로 변경할 수 있습니다.

Docker 빌드와 health endpoint까지 한 번에 검증하려면 smoke 스크립트를 실행합니다.
이 스크립트는 compose stack을 `up --build`로 띄운 뒤 backend `/api/health`와
frontend `/_stcore/health`가 응답하는지 확인하고, 종료 시 stack을 정리합니다.
성공 증거는 `artifacts/docker_smoke_verification.json`에 저장됩니다.

```bash
./scripts/docker-smoke.sh
```

성공 시 아래 형식의 로그가 남습니다.

```text
docker_smoke_started project=finagent-smoke compose_file=.../backend/docker-compose.yml
NAME                         IMAGE                      SERVICE    STATUS
finagent-smoke-backend-1     finagent-smoke-backend     backend    Up ... (healthy)
finagent-smoke-frontend-1    finagent-smoke-frontend    frontend   Up ... (healthy)
finagent-smoke-postgres-1    postgres:16-alpine         postgres   Up ... (healthy)
docker_smoke_passed backend=http://127.0.0.1:18000/api/health frontend=http://127.0.0.1:18501/_stcore/health
docker_smoke_evidence output_path=.../artifacts/docker_smoke_verification.json
```

동일한 검증은 `.github/workflows/docker-smoke.yml`에서도 수동 실행하거나 Docker 관련
파일 변경 PR에서 실행할 수 있습니다.

### 7. 개별 개발 실행

```bash
./scripts/setup-env.sh
./scripts/setup-db.sh up
.venv/bin/python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
.venv/bin/python -m streamlit run frontend/main.py --server.address 0.0.0.0 --server.port 8501
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
  "status": "ok",
  "workflow_job_runner": {
    "running": true,
    "stop_requested": false,
    "job_timeout_seconds": 300.0,
    "last_error": null,
    "last_error_at": null,
    "current_job": null
  }
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
  "message": null,
  "step_summary": null
}
```

`status`는 `queued`, `running`, `succeeded`, `failed` 중 하나입니다.

### `GET /api/v1/workflows/jobs/{job_id}/stream`

비동기 job 진행 상황을 SSE(`text/event-stream`)로 구독합니다. 이벤트 이름은
`queued`, `running`, `progress`, `complete`, `error` 중 하나이며, `data`에는
`GET /api/v1/workflows/jobs/{job_id}`와 동일한 job 상태 payload가 들어갑니다.

```text
event: progress
data: {"job_id":"job-123456789abc","status":"running","step_summary":{"success":2,"partial":0,"failed":0,"fallback":0,"completed":2}}
```

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

`decision`, `credit_grade`, `report`, `validation_result` 같은 최종 산출물은
성공한 job의 `context` 내부에 들어갑니다. Validation 재시도 소진 시 job은
`failed / VALIDATION_FAILED`가 되며 결과 endpoint는 `409 JOB_FAILED`를 반환합니다.

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
docker compose -f backend/docker-compose.yml config --quiet
```

모든 Python 실행/검증 명령은 `.venv/bin/...` 기준으로 실행합니다.

산업 RAG 평가 예시는 다음과 같습니다. 상세한 데이터셋 계약과 메트릭은 [산업 방법론 RAG 문서](docs/rag/industry-methodology.md)를 참고합니다.

```bash
.venv/bin/python -m backend.scripts.evaluate_industry_rag \
  backend/rag/eval_datasets/industry_methodology.jsonl \
  --target retriever
```

고정 retriever/agent RAGAS 결과 artifact를 모두 재생성하려면 다음 명령을 사용합니다.

```bash
.venv/bin/python -m backend.scripts.regenerate_industry_rag_artifacts
```

재생성 결과는 `backend/rag/artifacts/industry_rag_eval/` 아래의 `report.json`,
`agent_report.json`, `regeneration_manifest.json`에서 확인합니다.

`frontend/`는 현재 Python Streamlit 앱이므로 `npm run lint` 대상이 아닙니다.

## 관련 문서

- [워크플로우](docs/domain/workflows.md)
- [유스케이스 명세](docs/design/use-case-specification.md)
- [컴포넌트 설계](docs/design/component-design.md)
- [인터페이스 정의](docs/design/interface-definition.md)
- [시퀀스 다이어그램](docs/design/sequence-diagram.md)
- [ERD](docs/design/erd.md)
