# FinAgent-SME

FinAgent-SME는 중소기업 대상 B2B 거래 리스크 심사를 지원하는 멀티 에이전트 시스템입니다. 은행·금융기관 심사 담당자가 기업 정보를 빠르게 수집하고, 오케스트레이터 기반 워크플로우를 실행해 심사 판단에 필요한 결과를 확인하는 것을 목표로 합니다.

## 현재 상태

- 백엔드: FastAPI API와 에이전트 모듈 제공
- 프론트엔드: Streamlit 검색/리포트 UI 제공
- 기본 실행 흐름: 프론트 `검색` 버튼 -> `/api/v1/workflows/orchestrator` -> `run_credit_workflow()`
- 기본 오케스트레이터 단계: `CollectorAgent`
- 선택 단계: `pdf_path`가 있을 때 `MultiModalDocumentAgent`

재무 분석, 산업 분석, 리스크 이벤트 모듈은 저장소에 포함되어 있지만 현재 기본 프론트 검색 흐름에 자동 연결되지는 않습니다.

## 저장소 구조

```text
FinAgent-SME/
├── backend/     # FastAPI, 에이전트, 오케스트레이터, DB compose
├── frontend/    # Streamlit UI
├── tests/       # pytest 및 수동 검증용 테스트 자료
├── docs/        # 규칙, 워크플로우, 설계 문서
├── setup.sh     # 로컬 실행/종료 스크립트
└── requirements.txt
```

각 디렉터리의 상세 설명은 아래 문서를 참고하면 됩니다.

- [backend/README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/backend/README.md)
- [frontend/README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/frontend/README.md)
- [tests/README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/tests/README.md)

## 요구사항

- Python 3.11+
- Docker Desktop 또는 `docker compose`
- OpenDART, OpenAI, ECOS, KOSIS 사용 시 해당 API 키

## 빠른 시작

가장 쉬운 실행 방법은 루트에서 `setup.sh`를 사용하는 방식입니다.

```bash
./setup.sh
```

위 명령은 필요 시 `.venv`를 만들고 의존성을 설치한 뒤, 다음 서비스를 함께 시작합니다.

- PostgreSQL 컨테이너
- FastAPI 백엔드
- Streamlit 프론트엔드

기본 주소:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:8501`
- Swagger: `http://localhost:8000/docs`

## 자주 쓰는 명령

```bash
./setup.sh install
./setup.sh up
./setup.sh down
./setup.sh restart
./setup.sh status
./setup.sh logs
./setup.sh db-up
./setup.sh db-down
./setup.sh db-status
./setup.sh db-logs
```

`./setup.sh down`은 프론트, 백엔드, PostgreSQL을 순서대로 함께 중지합니다.

## 환경 변수

백엔드 설정은 주로 `backend/.env`를 사용합니다.

```env
OPENAI_API_KEY=...
OPEN_DART_API_KEY=...
ECOS_API_KEY=...
KOSIS_API_KEY=...
DATABASE_URL=...
```

또는 PostgreSQL 접속 정보를 아래 값들로 나눠서 줄 수 있습니다.

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=finagent
POSTGRES_PASSWORD=finagent
POSTGRES_DB=finagent
```

시작 전 예시 파일이 필요하면 다음처럼 준비합니다.

```bash
cp backend/.env.example backend/.env
```

## 개발 실행

전체 스택 대신 각각 실행하려면 아래처럼 사용할 수 있습니다.

```bash
./setup.sh install
./setup.sh db-up
cd backend && ../.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
cd frontend && ../.venv/bin/python -m streamlit run main.py --server.address 0.0.0.0 --server.port 8501
```

## 테스트와 품질 확인

```bash
.venv/bin/pytest tests/
.venv/bin/ruff check backend frontend tests
```

일부 테스트는 외부 API 키 없이도 동작하지만, 일부 수동 검증 스크립트는 실제 API 자격 증명이 필요합니다. 자세한 내용은 [tests/README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/tests/README.md)에 정리되어 있습니다.

## 문서 기준

- [docs/conventions/naming.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/docs/conventions/naming.md)
- [docs/conventions/error-handling.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/docs/conventions/error-handling.md)
- [docs/conventions/testing.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/docs/conventions/testing.md)
- [docs/domain/workflows.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/docs/domain/workflows.md)
