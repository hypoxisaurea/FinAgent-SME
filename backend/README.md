# Backend

`backend/`는 FinAgent-SME의 FastAPI API, LangGraph 오케스트레이터, 도메인 agent, DB/service 계층을 담고 있습니다.

## 현재 백엔드 역할

- FastAPI 앱 제공
- 신용 심사 워크플로우 실행
- 기업 마스터/기업개황/재무 피처 DB 구축
- 산업 신용평가방법론 PDF 적재·검색·RAGAS 평가
- 뉴스 수집 및 리스크 분석
- 최종 판단, 리포트 생성, 검증 및 Langfuse score 기록

## 요청 흐름

1. 프론트가 `POST /api/v1/workflows/jobs`를 호출합니다.
2. API 계층이 `request_id`를 바인딩하고 job row를 `queued` 상태로 등록합니다.
3. 앱 startup 시 시작된 `workflow_job_runner`가 queued job을 claim 합니다.
4. runner가 background thread에서 `run_credit_workflow()`를 실행합니다.
5. `CompanyResolverAgent`가 `sme_list`와 `company_profiles` 기반으로 기업을 식별합니다.
6. 식별 성공 시 `news_collector`, `financial_analyst`가 시작 노드로 실행되고, 내부 payload에 `pdf_path`가 있으면 `multimodal_document`도 함께 실행됩니다.
7. `risk_event`는 뉴스 결과 이후, `industry_analyst`는 재무 결과 이후 실행됩니다.
8. `decision` -> `report` -> `validation`이 순차 실행됩니다. 검증 실패 시 기본 1회 `report` 생성과 검증을 재실행합니다.
9. 재검증 실패는 판단/보고서를 차단하고, runner가 job을 `failed / VALIDATION_FAILED`로 마감합니다. 그 외 결과는 `succeeded`로 저장합니다.
10. 프론트는 `GET /api/v1/workflows/jobs/{job_id}`와 `/result`를 polling/fetch 합니다.

참고:

- `POST /api/v1/workflows/orchestrator`
- `POST /api/v1/workflows/credit-assessment`

위 두 동기 엔드포인트는 호환 및 직접 디버깅 용도로 유지되고 있습니다.

## 디렉터리 구조

```text
backend/
├── main.py
├── api/
├── agents/
├── common/
├── data/
├── integrations/
├── rag/
├── rag_docs/
├── schemas/
├── scripts/
├── tools/
└── docker-compose.yml
```

## 주요 모듈

### `main.py`

- FastAPI 앱 생성
- CORS 등록
- 요청별 `X-Request-ID` 바인딩
- startup/shutdown 시 workflow job runner 시작/종료
- 종료 시 Langfuse shutdown 처리

### `api/routes/workflows.py`

- `POST /api/v1/workflows/jobs`
- `GET /api/v1/workflows/jobs/{job_id}`
- `GET /api/v1/workflows/jobs/{job_id}/result`
- `POST /api/v1/workflows/orchestrator`
- `POST /api/v1/workflows/credit-assessment`
- 입력 오류를 `400`, 내부 예외를 `500`으로 매핑

### `agents/orchestrator/`

- `orchestrator.py`: 워크플로우 팩토리와 실행 진입점
- `graph.py`: LangGraph 노드/엣지 구성
- `step_runner.py`: timeout/retry/error-code 정규화
- `results.py`: 최종 상태/응답 조립

### `agents/`

- `company_resolver`: 기업 마스터 조회
- `news_collector`: 뉴스 수집과 적재
- `financial_analyst`: 재무 분석과 `grade_cap` 산출
- `industry_analyst`: KSIC/산업 평균/거시 지표 분석
- `risk_event`: 뉴스 기반 리스크 이벤트 탐지
- `decision`: 승인/검토/거절과 등급/한도 산출
- `report`: 사람이 읽기 쉬운 리포트 생성
- `validation`: 결과 정합성 검사와 Langfuse score 기록
- `multimodal_document`: 내부 payload에 `pdf_path`가 있을 때만 추가

### `data/`

- `db.py`: DB URL 해석과 테이블 상수
- `repositories/`: 직접 SQL 실행과 DataFrame 저장
- `services/`: 기업 조회, DB 구축 use case, workflow job submit/status/result
- `repositories/workflow_job.py`: workflow job row 저장/조회
- `services/workflow_job_runner.py`: queued job background worker

### `common/`

- `env.py`: `backend/.env` 해석의 canonical source
- `settings.py`: 앱 설정
- `logging.py`: request_id 기반 구조화 로깅
- `contracts.py`: agent 공통 실행 contract
- `tool_runtime.py`: tool fallback/실행 메타데이터
- `langfuse.py`: trace, observation, score wrapper

### `rag/`

- `chroma_client.py`: `industry_knowledge` collection과 Ko-SRoBERTa 임베딩
- `ingest_industry_docs.py`: 방법론 PDF를 페이지 단위로 읽고 중복 없이 청크 적재
- `retriever.py`: 업종 metadata와 의미 검색을 결합해 요약·평가요소·출처 반환
- `evaluation.py`: retriever와 `IndustryAnalystAgent`의 RAGAS 평가

자세한 실행 절차와 데이터셋 계약은 [산업 방법론 RAG 문서](../docs/rag/industry-methodology.md)를 참고합니다.

## 주요 엔드포인트

- `GET /`
- `GET /api/health`
- `POST /api/v1/workflows/jobs`
- `GET /api/v1/workflows/jobs/{job_id}`
- `GET /api/v1/workflows/jobs/{job_id}/result`
- `POST /api/v1/workflows/orchestrator`
- `POST /api/v1/workflows/credit-assessment`
- `GET /docs`

## 응답 구조 메모

### 1. Job submit 응답

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

### 2. Job status 응답

```json
{
  "job_id": "job-...",
  "request_id": "req-...",
  "company_name": "회사명",
  "status": "queued | running | succeeded | failed",
  "submitted_at": "2026-06-13T00:00:00+00:00",
  "started_at": null,
  "finished_at": null,
  "error_code": null,
  "message": null,
  "step_summary": null
}
```

### 3. 최종 workflow 결과 응답

```json
{
  "request_id": "req-...",
  "company_name": "회사명",
  "status": "success | partial | failed | not_target",
  "context": {},
  "steps": []
}
```

- 최종 산출물은 `context` 내부에 누적됩니다.
- `steps[*]`에는 `agent_name`, `ok`, `status`, `error_code`, `fallback_used`, `latency_ms`, `output`, `error`가 포함됩니다.
- `not_target` 또는 validation 차단일 때 `code`, `message`가 함께 반환됩니다.
- `GET /api/v1/workflows/jobs/{job_id}/result`는 job이 `succeeded`일 때만 workflow 결과를 반환합니다.

## 상태 계산 규칙

- `not_target`: `CompanyResolverAgent`가 기업 미존재를 반환한 경우
- `success`: 유효한 최종 validation을 포함한 모든 유효 step의 `ok=True`
- `partial`: `ok=True`와 `ok=False` step이 혼재한 경우
- `failed`: 모든 step이 실패했거나 validation gate가 결과를 차단한 경우

주의:

- agent 단위 `partial`이나 `fallback_used=true`가 있어도 step이 `ok=True`이면 전체 workflow 상태는 `success`로 계산될 수 있습니다.
- validation 재검증이 통과하면 이전 validation 실패 step은 이력에 남지만 상태 집계에서는 제외됩니다.
- 현재 `continue_on_error`는 내부 워크플로우 옵션이며 공개 API 바디에서는 조정하지 않습니다.

## Job 상태 규칙

- `queued`: DB에 등록됐지만 아직 worker가 claim 하지 않음
- `running`: worker가 claim 했고 workflow 실행 중
- `succeeded`: 최종 workflow 결과 저장 완료
- `failed`: 입력 오류 또는 workflow 실행 오류로 종료

## 환경 변수

```env
OPEN_ROUTER_API_KEY=...
OPEN_ROUTER_BASE_URL=https://openrouter.ai/api/v1
OPEN_ROUTER_MODEL=openai/gpt-4o-mini
OPEN_DART_API_KEY=...
ECOS_API_KEY=...
KOSIS_API_KEY=...
DATABASE_URL=...
POSTGRES_HOST=...
POSTGRES_PORT=5432
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

- 신규 LLM 설정은 `OPEN_ROUTER_API_KEY` 기준입니다.
- `OPEN_AI_API_KEY`, `OPENAI_API_KEY`, `OPEN_API_KEY`는 레거시 호환용 fallback입니다.

## 실행

루트에서:

```bash
./scripts/setup-env.sh
./scripts/setup-db.sh up
./scripts/run-server.sh up
```

백엔드만 직접 실행:

```bash
./.venv/bin/python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Docker 이미지와 전체 Compose 스택 실행:

```bash
docker build -f backend/Dockerfile -t finagent-backend .
docker compose -f backend/docker-compose.yml up --build -d
docker compose -f backend/docker-compose.yml logs -f backend
```

Compose의 backend는 `postgres:5432`를 사용하며 `backend/.env`의 외부 API와
Langfuse 설정을 전달받습니다. `backend/.env`는 build context에서 제외되어 이미지에
포함되지 않습니다.

Backend 이미지는 RAG embedding 실행을 위해 `torch 2.12.1+cpu`를 먼저 설치합니다.
일반 requirements 해석으로 CUDA 패키지가 유입되지 않도록 CPU wheel index를 명시하며,
PDF 처리를 위해 Ghostscript와 ImageMagick을 포함합니다.

주의:

- 현재 worker는 FastAPI 앱 프로세스 안에서 같이 실행됩니다.
- 따라서 job 처리를 위해서는 API 서버가 떠 있어야 합니다.

## DB 구축

```bash
./scripts/setup-db.sh build --year 2024 --sample-size 10
```

현재 파이프라인은 다음 테이블을 다룹니다.

- `sme_list`
- `company_profiles`
- `financial_features`
- `financial_statement_details`
- `financial_error_logs`
- `daum_news_articles`

## 산업 RAG

방법론 PDF 적재:

```bash
.venv/bin/python -m backend.rag.ingest_industry_docs
```

Retriever 평가:

```bash
.venv/bin/python -m backend.scripts.evaluate_industry_rag \
  backend/rag/eval_datasets/industry_methodology.jsonl \
  --target retriever \
  --output-path backend/rag/artifacts/industry_rag_eval/report.json
```

기본 벡터 저장소는 `backend/vectorstore/industry_knowledge/`입니다. 평가에는 LLM API 키가 필요하며, 최초 적재에는 임베딩 모델 다운로드가 발생할 수 있습니다.

## 품질 확인

```bash
.venv/bin/ruff check backend tests
.venv/bin/pytest -o cache_dir=.cache/pytest tests/
```
