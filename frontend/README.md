# Frontend

`frontend/`는 FinAgent-SME의 Streamlit 기반 UI입니다. 현재는 검색 화면과 결과 화면 두 페이지를 세션 상태로 전환하는 단순한 구조이며, 검색 버튼을 누르면 백엔드 오케스트레이터 API를 호출합니다.

## 현재 화면 구성

- 검색 화면: 회사명 입력, 헬스 체크, 오케스트레이터 실행
- 결과 화면: 응답 JSON, 단순 요약, 리스트/딕셔너리 결과 표시, JSON 다운로드

## 파일 구조

```text
frontend/
├── main.py
├── streamlit_ui.py
└── views/
    ├── search.py
    └── report.py
```

## 동작 흐름

1. `main.py`가 Streamlit 앱을 초기화합니다.
2. `st.session_state.base_url` 기본값은 `http://localhost:8000`입니다.
3. 검색 화면에서 `검색` 버튼을 누르면 `views/search.py`가 `/api/v1/workflows/orchestrator`로 POST 요청을 보냅니다.
4. 응답은 `st.session_state.last_result`에 저장됩니다.
5. 앱은 Report 화면으로 이동해 결과를 렌더링합니다.

## 실행 방법

전체 스택 실행:

```bash
./setup.sh
```

프론트만 실행:

```bash
./setup.sh install
cd frontend
../.venv/bin/python -m streamlit run main.py --server.address 0.0.0.0 --server.port 8501
```

종료:

```bash
./setup.sh down
```

## 백엔드 의존성

기본적으로 아래 백엔드가 떠 있어야 검색 기능이 정상 동작합니다.

- API base URL: `http://localhost:8000`
- Health check: `GET /api/health`
- Workflow endpoint: `POST /api/v1/workflows/orchestrator`

## UI 메모

- Streamlit 기본 사이드바는 `streamlit_ui.py`에서 숨깁니다.
- 별도 멀티페이지 라우터 대신 `st.session_state.page`를 사용합니다.
- 결과 페이지는 오케스트레이터 원본 응답을 우선 보여주는 디버그 친화적인 형태입니다.

## 향후 개선 포인트

- 백엔드 주소를 UI에서 수정할 수 있는 입력 필드
- 단계별 진행 상태 표시
- 결과 요약 카드와 차트 시각화
- 문서 업로드와 `pdf_path` 연동
- 에러 응답 포맷을 사용자 친화적으로 가공

## 개발 확인

```bash
.venv/bin/ruff check frontend
```

프론트는 별도 JS 빌드가 없는 Python Streamlit 앱이므로, 현재 저장소 기준 `npm run lint` 대상은 아닙니다.

## 참고 문서

- [README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/README.md)
- [backend/README.md](/Users/princess1004/Desktop/MY/Projects/FinAgent-SME/backend/README.md)
