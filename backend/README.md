# Backend

`backend/`는 FinAgent-SME의 FastAPI API, 오케스트레이터, 에이전트 구현을 담고 있습니다. 현재 프론트의 검색 요청은 이 디렉터리의 워크플로우 API를 호출해 오케스트레이터를 실행합니다.

## 핵심 역할

- FastAPI 앱 제공
- 오케스트레이터 기반 심사 워크플로우 실행
- 기업 마스터/재무 DB 구축 파이프라인 실행
- 대상 기업 뉴스 수집 파이프라인 실행
- 선택적 멀티모달 문서 처리
- 재무/산업/리스크/리포트 에이전트 실행

## 현재 요청 흐름

1. 프론트에서 회사명을 입력하고 `검색` 버튼을 누릅니다.
2. `POST /api/v1/workflows/orchestrator`가 호출됩니다.
3. API 라우터가 `run_credit_workflow(company_name)`를 실행합니다.
4. 오케스트레이터가 먼저 `CompanyResolverAgent`로 대상 기업 여부를 판별합니다.
5. 대상 기업이면 `NewsCollectorAgent`, `FinancialAnalystAgent`, `MultiModalDocumentAgent(optional)`를 1차 병렬 실행합니다.
6. 이어서 `NewsCollectorAgent` 결과를 입력으로 `RiskEventAgent`, `FinancialAnalystAgent` 결과를 입력으로 `IndustryAnalystAgent`를 실행합니다.
7. 분석 종단 노드 결과가 모이면 `DecisionAgent`, `ReportAgent`를 순차 실행합니다.

## 실행 방법

루트 기준 전체 스택 실행:

```bash
./scripts/run-all.sh up
```

백엔드만 개발 모드로 실행:

```bash
./scripts/setup-env.sh
./scripts/setup-db.sh up
cd backend
../.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

종료:

```bash
./scripts/run-server.sh down
./scripts/setup-db.sh down
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
    ├── company_registry/
    ├── company_resolver/
    ├── news_collector/
    ├── multimodal_document/
    ├── orchestrator/
    ├── financial_analyst/
    ├── industry_analyst/
    ├── report/
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
- 대상 기업 판별 후 LangGraph 기반 DAG로 병렬·의존 단계를 관리
- `DecisionAgent`, `ReportAgent` 후속 단계 실행
- `success`, `partial`, `failed`, `not_target` 상태 계산

### `agents/company_resolver/agent.py`

- 기업명을 기준으로 기업 마스터 테이블 조회
- `corp_code`, `corp_name` 확보
- 미존재 시 `not_target` 상태로 종료

### `agents/company_registry/`

- 기업 마스터(`sme_list`) 및 재무 피처 DB 구축 담당
- DART 기반 배치 수집 파이프라인 보관
- 조회용 DB 유틸도 이 영역 기준으로 사용

### `agents/news_collector/`

- 대상 기업 뉴스 수집 전용 에이전트
- 오케스트레이터 병렬 분석 단계에서 사용
- 현재 뉴스 파이프라인은 placeholder 구조를 유지

### `agents/multimodal_document/`

- `pdf_path`가 있을 때 문서 분석 수행
- 텍스트, 차트 이미지, 페이지 수 등을 반환

### `agents/financial_analyst/`

- 재무제표, 비율, 추세, `grade_cap` 분석
- 오케스트레이터 병렬 분석 단계에서 사용

### `agents/industry_analyst/`

- 업종 매핑, 산업 평균, 업황, 경기 국면, 거시 지표 분석
- 오케스트레이터 병렬 분석 단계에서 사용

### `agents/risk_event/`

- 뉴스·공시·법적·재무 이상 징후를 통합 분석
- 심각도 분류, 타임라인, 전체 리스크 수준 집계

### `agents/report/`

- `DecisionAgent` 결과와 중간 분석 결과를 묶어 최종 리포트 생성

## 환경 변수

`backend/.env`에서 주로 다음 값을 사용합니다.

```env
OPEN_AI_API_KEY=...
OPEN_DART_API_KEY=...
ECOS_API_KEY=...
KOSIS_API_KEY=...
DATABASE_URL=...
```

## DB 실행

PostgreSQL 컨테이너는 `backend/docker-compose.yml`로 관리합니다.

```bash
./scripts/setup-db.sh up
./scripts/setup-db.sh build
./scripts/setup-db.sh status
./scripts/setup-db.sh down
```

기본 컨테이너 이름은 `finagent-postgres`입니다.

빠른 점검용 샘플 실행:

```bash
./scripts/setup-db.sh build --sample-size 10
```

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
