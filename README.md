# FinAgent-SME

FinAgent-SME는 중소기업 대상 B2B 거래 리스크 심사를 지원하는 멀티 에이전트 시스템입니다. 은행·금융기관 심사 담당자가 기업 정보를 빠르게 수집하고, 오케스트레이터 기반 워크플로우를 실행해 심사 판단에 필요한 결과를 확인하는 것을 목표로 합니다.

## 현재 상태

- 백엔드: FastAPI API와 에이전트 모듈 제공
- 프론트엔드: Streamlit 검색/리포트 UI 제공
- 기본 실행 흐름: 프론트 `검색` 버튼 -> `/api/v1/workflows/orchestrator` -> `run_credit_workflow()`
- 현재 오케스트레이터 흐름:
  - `CompanyResolverAgent`로 대상 기업 여부 판별
  - 병렬 분석: `NewsCollectorAgent`, `FinancialAnalystAgent`, `IndustryAnalystAgent`, `RiskEventAgent`
  - 후속 단계: `DecisionAgent`, `ReportAgent`
  - 선택 단계: `pdf_path`가 있을 때 `MultiModalDocumentAgent`

기업 마스터/재무 DB 구축용 배치 에이전트는 `company_registry`, 런타임 뉴스 수집은 `news_collector`로 분리되어 있습니다.

## 저장소 구조

```text
FinAgent-SME/
├── backend/     # FastAPI, 에이전트, 오케스트레이터, DB compose
├── frontend/    # Streamlit UI
├── tests/       # pytest 및 수동 검증용 테스트 자료
├── docs/        # 규칙, 워크플로우, 설계 문서
├── scripts/     # 로컬 실행/세팅 스크립트 모음
└── requirements.txt
```

`backend/`는 현재 역할 기준으로 단순하게 묶여 있습니다.

- `common/`: env, settings, logging, 공통 agent/runtime 유틸
- `agents/`: 워크플로우별 agent 엔트리포인트
- `tools/`: 재무/산업/뉴스/기업구축 도구와 프롬프트
- `data/`: DB 연결, repository, service 계층
- `api/`, `integrations/`, `schemas/`, `scripts/`: API/외부연동/계약/실행 진입점

## 설계 문서

- 워크플로우 기준 문서: `docs/domain/workflows.md`
- 유스케이스 명세서: `docs/design/use-case-specification.md`
- 컴포넌트 설계서: `docs/design/component-design.md`
- 인터페이스 정의서: `docs/design/interface-definition.md`
- 시퀀스 다이어그램: `docs/design/sequence-diagram.md`
- ERD: `docs/design/erd.md`

## 요구사항

- Python 3.13+
- Docker Desktop 또는 `docker compose`
- OpenDART, OpenAI, ECOS, KOSIS 사용 시 해당 API 키

## 실행 방법

> [!IMPORTANT]
> 아래 모든 명령은 프로젝트 루트 `FinAgent-SME/`에서 실행합니다.

### 1. 환경 변수 준비

백엔드 설정은 주로 `backend/.env`를 사용합니다.

```env
OPEN_AI_API_KEY=...
OPEN_DART_API_KEY=...
ECOS_API_KEY=...
KOSIS_API_KEY=...
DATABASE_URL=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
```

시작 전 예시 파일이 필요하면 다음처럼 준비합니다.

```bash
cp backend/.env.example backend/.env
```

> [!NOTE]
> `DATABASE_URL`을 직접 넣지 않아도 `backend/docker-compose.yml`의 기본 PostgreSQL 설정으로 로컬 실행은 가능합니다.
> 외부 DB를 쓰거나 포트를 바꾸는 경우에는 `backend/.env` 값도 함께 맞춰주세요.

### 2. 환경 세팅만 먼저 하기

가상환경 생성과 Python 의존성 설치만 먼저 하려면 아래 명령을 실행합니다.

```bash
./scripts/setup-env.sh
```

> [!TIP]
> 테스트 실행이나 코드 확인이 목적이라면 이 단계만 먼저 해도 됩니다.

### 3. DB만 실행하기

PostgreSQL 컨테이너만 따로 실행하려면 아래 명령을 사용합니다.

```bash
./scripts/setup-db.sh up
```

DB 상태 확인, 로그 확인, 종료 명령은 아래와 같습니다.

```bash
./scripts/setup-db.sh status
./scripts/setup-db.sh logs
./scripts/setup-db.sh down
```

기업 마스터/재무 DB를 실제로 채우려면 DB를 띄운 뒤 아래 명령을 실행합니다.

```bash
./scripts/setup-db.sh build --year 2024 --sample-size 10
```

> [!WARNING]
> `build`는 DART 기반 수집과 DB 저장을 수행하므로 API 키, 네트워크, DB 연결 상태가 모두 준비되어 있어야 합니다.

### 4. 백엔드와 프론트엔드만 실행하기

DB가 이미 떠 있는 상태에서 앱 서버만 실행하려면 아래 명령을 사용합니다.

```bash
./scripts/run-server.sh up
```

상태 확인, 로그 확인, 종료 명령은 아래와 같습니다.

```bash
./scripts/run-server.sh status
./scripts/run-server.sh logs
./scripts/run-server.sh down
```

> [!NOTE]
> `run-server.sh up`는 환경 세팅까지 확인한 뒤 백엔드와 프론트를 실행합니다.
> 다만 DB는 자동으로 올리지 않으므로 먼저 `./scripts/setup-db.sh up`을 실행해야 검색 기능이 정상 동작합니다.

### 5. 전체를 한 번에 실행하기

환경 세팅, PostgreSQL, 백엔드, 프론트엔드를 한 번에 올리려면 아래 명령을 사용합니다.

```bash
./scripts/run-all.sh up
```

전체 상태 확인과 종료는 아래 명령을 사용합니다.

```bash
./scripts/run-all.sh status
./scripts/run-all.sh down
```

> [!TIP]
> 처음 프로젝트를 띄워보는 경우에는 `./scripts/run-all.sh up`가 가장 단순한 시작 방법입니다.

### 6. 개발 모드로 개별 실행하기

스크립트 대신 프로세스를 직접 띄우고 싶다면 아래 순서로 실행할 수 있습니다.

```bash
./scripts/setup-env.sh
./scripts/setup-db.sh up
./scripts/setup-db.sh build --year 2024 --sample-size 10
./.venv/bin/python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
cd frontend && ../.venv/bin/python -m streamlit run main.py --server.address 0.0.0.0 --server.port 8501
```

### 7. 접속 주소

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:8501`
- Swagger: `http://localhost:8000/docs`

## 자주 쓰는 명령

```bash
./scripts/setup-env.sh
./scripts/setup-db.sh up
./scripts/setup-db.sh build --sample-size 10
./scripts/setup-db.sh status
./scripts/setup-db.sh down
./scripts/run-server.sh up
./scripts/run-server.sh status
./scripts/run-server.sh logs
./scripts/run-server.sh down
./scripts/run-all.sh up
./scripts/run-all.sh down
```

## 테스트와 품질 확인

```bash
.venv/bin/pytest tests/
.venv/bin/pytest tests/ --cov=backend --cov-report=term-missing --cov-fail-under=40
.venv/bin/ruff check backend frontend tests
```

GitHub Actions CI(`.github/workflows/ci.yml`)에서도 PR/Push마다 `ruff`와 coverage gate 포함 `pytest`를 자동 실행합니다.
