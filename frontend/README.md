# Frontend

`frontend/`는 FinAgent-SME의 Streamlit 기반 UI입니다. 현재는 검색 화면과 리포트 화면 두 단계로 구성된 Python 프론트엔드입니다.

## 현재 화면 구성

- 검색 화면
  - 회사명 입력
  - 백엔드 헬스 체크
  - 심사 job 접수
  - job 상태 SSE stream 및 polling fallback
- 결과 화면
  - 심사 요약 카드
  - 리스크/권고/검증 정보
  - Raw JSON 표시
  - JSON 다운로드
  - 브라우저 인쇄용 PDF 렌더링 버튼

## 파일 구조

```text
frontend/
├── main.py
├── streamlit_ui.py
└── views/
    ├── search.py
    └── report.py
```

## 동작 방식

1. `main.py`가 앱과 세션 상태를 초기화합니다.
2. 기본 `base_url`은 `http://localhost:8000`입니다.
3. 검색 화면에서 `검색` 버튼을 누르면 `views/search.py`가 `POST /api/v1/workflows/jobs`를 호출합니다.
4. 반환된 `job_id`는 `st.session_state.pending_job_id`에 저장됩니다.
5. 검색 화면은 `GET /api/v1/workflows/jobs/{job_id}/stream` SSE 이벤트를 우선 수신합니다.
6. SSE 연결이 어려우면 `GET /api/v1/workflows/jobs/{job_id}`를 2초 간격으로 polling 합니다.
7. job이 `succeeded`가 되면 `GET /api/v1/workflows/jobs/{job_id}/result`를 호출합니다.
7. 최종 응답은 `st.session_state.last_result`에 저장됩니다.
8. `views/report.py`가 `context.report`, `context.decision`, `steps`를 조합해 결과를 렌더링합니다.

Streamlit 구조상 브라우저 네이티브 `EventSource`가 아니라 서버 프로세스의
`requests(stream=True)` 기반 SSE client를 사용합니다. SSE parsing과 HTTP 소비 계약은
`frontend/services/workflow_stream.py`에 분리되어 있으며, 수신 이벤트는 검색 화면의
`SSE 실시간 진행 로그`와 진행률 UI에 반영됩니다.

## 백엔드 의존성

- Health check: `GET /api/health`
- Job submit: `POST /api/v1/workflows/jobs`
- Job stream: `GET /api/v1/workflows/jobs/{job_id}/stream`
- Job status: `GET /api/v1/workflows/jobs/{job_id}`
- Job result: `GET /api/v1/workflows/jobs/{job_id}/result`
- 최종 응답 구조: `status`, `context`, `steps`, `request_id`
- 상태 응답 구조: `job_id`, `status`, `submitted_at`, `started_at`, `finished_at`, `error_code`, `message`, `step_summary`

UI가 가져오는 `succeeded` 결과에는 `decision`, `credit_grade`, `recommended_limit`,
`report`, `validation_result`가 `context`에 포함됩니다. Validation 차단 결과는 job이
`failed`가 되어 결과 화면으로 이동하지 않고 검색 화면에서 상태 메시지를 표시합니다.

## 실행

루트에서 전체 스택 실행:

```bash
./scripts/run-all.sh up
```

프론트만 직접 실행:

```bash
.venv/bin/python -m streamlit run frontend/main.py --server.address 0.0.0.0 --server.port 8501
```

Docker 이미지 실행:

```bash
docker build -f frontend/Dockerfile -t finagent-frontend .
docker run --rm -p 8501:8501 \
  -e FINAGENT_BACKEND_URL=http://host.docker.internal:8000 \
  finagent-frontend
```

Compose에서는 `FINAGENT_BACKEND_URL=http://backend:8000`이 자동 설정됩니다.
환경 변수가 없으면 로컬 개발 기본값 `http://localhost:8000`을 사용합니다.

## 구현 메모

- 별도 JavaScript 번들링은 없습니다.
- 라우팅은 `st.session_state.page`로 처리합니다.
- 백엔드 호출은 브라우저가 아니라 Streamlit 서버 프로세스에서 `requests`로 수행합니다.
- 진행 상태는 SSE를 먼저 소비하고, 실패 시 `time.sleep(2)` 후 `st.rerun()` polling으로 fallback합니다.
- SSE client 검증 artifact는 `.venv/bin/python -m frontend.scripts.verify_workflow_stream`으로 생성합니다.
- 별도 API base URL 입력 UI는 아직 없습니다.

## 품질 확인

```bash
.venv/bin/ruff check frontend
```

현재 저장소 기준 프론트엔드는 `npm run lint` 대상이 아닙니다.
