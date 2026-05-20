# Backend

`backend/`는 FinAgent-SME의 FastAPI API, 오케스트레이터, 에이전트 구현을 담고 있습니다. 현재 프론트의 검색 요청은 이 디렉터리의 워크플로우 API를 호출해 오케스트레이터를 실행합니다.

## 핵심 역할

- FastAPI 앱 제공
- 오케스트레이터 기반 심사 워크플로우 실행
- DART/뉴스 수집 파이프라인 실행
- 선택적 멀티모달 문서 처리
- 재무/산업 분석 모듈 보관

## 현재 요청 흐름

1. 프론트에서 회사명을 입력하고 `검색` 버튼을 누릅니다.
2. `POST /api/v1/workflows/orchestrator`가 호출됩니다.
3. API 라우터가 `run_credit_workflow(company_name)`를 실행합니다.
4. 오케스트레이터가 기본적으로 `CollectorAgent`를 수행합니다.
5. `pdf_path`가 payload에 포함되면 `MultiModalDocumentAgent`가 추가로 실행됩니다.

## 실행 방법

루트 기준 전체 스택 실행:

```bash
./setup.sh
```

백엔드만 개발 모드로 실행:

```bash
./setup.sh install
./setup.sh db-up
cd backend
../.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

종료:

```bash
./setup.sh down
```

## 주요 엔드포인트

- `GET /` : 서비스 메타 정보
- `GET /api/health` : 헬스 체크
- `POST /api/v1/workflows/orchestrator` : 프론트가 사용하는 오케스트레이터 진입점
- `POST /api/v1/workflows/credit-assessment` : 동일 워크플로우를 호출하는 호환 엔드포인트
- `GET /docs` : Swagger UI

## 에러 처리

워크플로우 API는 현재 아래 규칙으로 응답합니다.

- 입력값 오류: `400`
- 오케스트레이터 실행 실패: `500`

응답 예시:

```json
{
  "detail": {
    "code": "INVALID_INPUT",
    "message": "입력값이 올바르지 않습니다.",
    "detail": {
      "company_name": "   "
    }
  }
}
```

상세 규칙은 [docs/conventions/error-handling.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/docs/conventions/error-handling.md)를 참고하면 됩니다.

## 디렉터리 구조

```text
backend/
├── main.py
├── config.py
├── backend_env.py
├── docker-compose.yml
├── api/
│   ├── router.py
│   └── routes/
├── schemas/
├── utils/
└── agents/
    ├── base.py
    ├── collector/
    ├── multimodal_document/
    ├── orchestrator/
    ├── financial_analyst/
    ├── industry_analyst/
    └── risk_event/
```

## 주요 모듈

### `main.py`

- FastAPI 앱 생성
- CORS 설정
- `/api` 라우터 등록

### `api/routes/workflows.py`

- 워크플로우 엔드포인트 정의
- `run_credit_workflow()` 호출
- 입력 오류와 내부 오류를 HTTP 에러로 매핑

### `agents/orchestrator/orchestrator.py`

- `WorkflowOrchestrator` 정의
- 단계별 `steps` 결과 집계
- `success`, `partial`, `failed`, `not_started` 상태 계산

### `agents/collector/agent.py`

- 현재 기본 오케스트레이터 단계
- `dart`, `news` 수집원을 조합 가능
- 기본 수집원은 `dart`

### `agents/multimodal_document/`

- `pdf_path`가 있을 때 문서 분석 수행
- 텍스트, 차트 이미지, 페이지 수 등을 반환

### `agents/financial_analyst/`, `agents/industry_analyst/`, `agents/risk_event/`

- 저장소에 구현이 존재하는 분석 모듈
- 현재 기본 프론트 검색 플로우에는 자동 연결되지 않음

## 환경 변수

`backend/.env`에서 주로 다음 값을 사용합니다.

```env
OPENAI_API_KEY=...
OPEN_DART_API_KEY=...
ECOS_API_KEY=...
KOSIS_API_KEY=...
DATABASE_URL=...
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=finagent
POSTGRES_PASSWORD=finagent
POSTGRES_DB=finagent
```

## DB 실행

PostgreSQL 컨테이너는 `backend/docker-compose.yml`로 관리합니다.

```bash
./setup.sh db-up
./setup.sh db-status
./setup.sh db-down
```

기본 컨테이너 이름은 `finagent-postgres`입니다.

## 테스트와 품질 확인

루트에서 실행:

```bash
.venv/bin/pytest tests/
.venv/bin/ruff check backend
```

워크플로우 API 회귀 테스트:

```bash
.venv/bin/pytest tests/test_workflows_api.py
```

## 참고 문서

- [README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/README.md)
- [tests/README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/tests/README.md)
- [docs/domain/workflows.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/docs/domain/workflows.md)
