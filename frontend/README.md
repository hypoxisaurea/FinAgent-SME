# Frontend

`frontend/`는 FinAgent-SME의 Streamlit 기반 UI입니다. 현재는 검색 화면과 리포트 화면 두 단계로 구성된 Python 프론트엔드입니다.

## 현재 화면 구성

- 검색 화면
  - 회사명 입력
  - 백엔드 헬스 체크
  - 오케스트레이터 실행
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
3. 검색 화면에서 `검색` 버튼을 누르면 `views/search.py`가 `POST /api/v1/workflows/orchestrator`를 호출합니다.
4. 응답은 `st.session_state.last_result`에 저장됩니다.
5. `views/report.py`가 `context.report`, `context.decision`, `steps`를 조합해 결과를 렌더링합니다.

## 백엔드 의존성

- Health check: `GET /api/health`
- Workflow endpoint: `POST /api/v1/workflows/orchestrator`
- 응답 구조: `status`, `context`, `steps`, `request_id`

현재 UI는 `decision`, `credit_grade`, `recommended_limit`, `report`, `validation_result`가 `context` 안에 있다는 전제에 맞춰 작성되어 있습니다.

## 실행

루트에서 전체 스택 실행:

```bash
./scripts/run-all.sh up
```

프론트만 직접 실행:

```bash
cd frontend
../.venv/bin/python -m streamlit run main.py --server.address 0.0.0.0 --server.port 8501
```

## 구현 메모

- 별도 JavaScript 번들링은 없습니다.
- 라우팅은 `st.session_state.page`로 처리합니다.
- 백엔드 호출은 브라우저가 아니라 Streamlit 서버 프로세스에서 `requests`로 수행합니다.
- 별도 API base URL 입력 UI는 아직 없습니다.

## 품질 확인

```bash
.venv/bin/ruff check frontend
```

현재 저장소 기준 프론트엔드는 `npm run lint` 대상이 아닙니다.
