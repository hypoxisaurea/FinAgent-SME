# Frontend (Streamlit)

이 디렉터리는 FinAgent-SME의 Streamlit 기반 심사 UI를 담고 있습니다. 현재 프론트엔드는 단일 엔트리 포인트에서 검색 화면과 리포트 화면을 전환하는 방식으로 동작합니다.

## 현재 구조

- `main.py`: Streamlit 앱 엔트리 포인트
- `streamlit_ui.py`: 페이지 공통 설정과 sidebar 숨김 처리
- `views/search.py`: 회사명 입력, 헬스 체크, 심사 요청 화면
- `views/report.py`: 심사 결과 JSON/요약 표시 및 다운로드 화면

## 가장 쉬운 실행 방법

프로젝트 루트에서 아래 명령을 실행하면 백엔드와 프론트가 함께 시작됩니다.

```bash
./setup.sh
```

중지나 상태 확인은 아래 명령을 사용합니다.

```bash
./setup.sh down
./setup.sh status
```

## 요구사항

- Python 3.11 이상
- 프로젝트 루트의 `requirements.txt`에 Streamlit과 관련 라이브러리가 추가되어 있어야 합니다.

## 가상환경 생성 (권장)

```bash
python -m venv .venv
source .venv/bin/activate
```

## 의존성 설치

```bash
pip install -r ../requirements.txt
```

> 참고: `requirements.txt`를 루트에서 사용합니다. 프론트엔드 전용 의존성 파일을 원하면 알려주세요.

## Streamlit 앱 실행

```bash
cd frontend
streamlit run main.py
```

기본 백엔드 주소는 `http://localhost:8000`입니다. 현재 UI에는 별도 입력 필드가 없으며, `main.py`에서 `st.session_state.base_url` 기본값으로 설정합니다.

## 화면 동작

1. 첫 화면에서 회사명을 입력합니다.
2. `Health 체크` 버튼으로 백엔드 연결 상태를 확인할 수 있습니다.
3. `검색` 버튼으로 `/api/v1/workflows/orchestrator`를 호출합니다.
4. 응답 결과는 세션에 저장되고, 같은 앱 안에서 리포트 화면으로 전환됩니다.
5. 리포트 화면에서는 원본 JSON, 단순 요약 테이블, 리스트형 데이터 표를 확인하고 JSON 다운로드를 할 수 있습니다.

## UI 메모

- Streamlit 기본 sidebar/navigation은 `streamlit_ui.py`에서 숨김 처리합니다.
- `views/` 디렉터리를 사용해 Streamlit의 자동 멀티페이지 sidebar 생성과 충돌하지 않도록 구성했습니다.

## 백엔드(개발) 실행 예시

```bash
# 프로젝트 루트에서
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 추가 개선 제안

- 백엔드 주소를 UI에서 변경할 수 있는 설정 입력 추가
- 결과 시각화(차트) 추가
- 파일 업로드(재무제표) 연동
- 인증 또는 사용자 세션 분리
