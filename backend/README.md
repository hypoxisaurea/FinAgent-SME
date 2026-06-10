# Backend

`backend/`는 FinAgent-SME의 FastAPI API, LangGraph 오케스트레이터, 도메인 agent, DB/service 계층을 담고 있습니다.

## 현재 백엔드 역할

- FastAPI 앱 제공
- 신용 심사 워크플로우 실행
- 기업 마스터/기업개황/재무 피처 DB 구축
- 뉴스 수집 및 리스크 분석
- 최종 판단, 리포트 생성, 검증 및 Langfuse score 기록

## 요청 흐름

1. 프론트가 `POST /api/v1/workflows/orchestrator`를 호출합니다.
2. API 계층이 `request_id`를 바인딩하고 `run_credit_workflow()`를 실행합니다.
3. `CompanyResolverAgent`가 `sme_list`와 `company_profiles` 기반으로 기업을 식별합니다.
4. 식별 성공 시 `news_collector`, `financial_analyst`가 시작 노드로 실행됩니다.
5. `risk_event`는 뉴스 결과 이후, `industry_analyst`는 재무 결과 이후 실행됩니다.
6. `decision` -> `report` -> `validation`이 순차 실행됩니다.
7. 최종 응답은 `status`, `context`, `steps`, `request_id`를 포함해 반환됩니다.

## 디렉터리 구조

```text
backend/
├── main.py
├── api/
├── agents/
├── common/
├── data/
├── integrations/
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
- 종료 시 Langfuse shutdown 처리

### `api/routes/workflows.py`

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
- `services/`: 기업 조회, DB 구축 use case

### `common/`

- `settings.py`: 앱 설정
- `logging.py`: request_id 기반 구조화 로깅
- `contracts.py`: agent 공통 실행 contract
- `tool_runtime.py`: tool fallback/실행 메타데이터
- `langfuse.py`: trace, observation, score wrapper

## 주요 엔드포인트

- `GET /`
- `GET /api/health`
- `POST /api/v1/workflows/orchestrator`
- `POST /api/v1/workflows/credit-assessment`
- `GET /docs`

## 응답 구조 메모

공개 워크플로우 응답은 현재 아래 구조를 기준으로 합니다.

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
- `not_target`일 때만 `code`, `message`가 함께 반환됩니다.

## 상태 계산 규칙

- `not_target`: `CompanyResolverAgent`가 기업 미존재를 반환한 경우
- `success`: 모든 step의 `ok=True`
- `partial`: `ok=True`와 `ok=False` step이 혼재한 경우
- `failed`: 모든 step의 `ok=False`

주의:

- agent 단위 `partial`이나 `fallback_used=true`가 있어도 step이 `ok=True`이면 전체 workflow 상태는 `success`로 계산될 수 있습니다.
- 현재 `continue_on_error`는 내부 워크플로우 옵션이며 공개 API 바디에서는 조정하지 않습니다.

## 환경 변수

```env
OPEN_AI_API_KEY=...
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

## DB 구축

```bash
./scripts/setup-db.sh build --year 2024 --sample-size 10
```

현재 파이프라인은 다음 테이블을 다룹니다.

- `sme_list`
- `company_profiles`
- `financial_features`
- `financial_error_logs`
- `daum_news_articles`

## 품질 확인

```bash
.venv/bin/ruff check backend tests
.venv/bin/pytest -o cache_dir=.cache/pytest tests/
```
