# Frontend (Streamlit)

이 디렉터리는 Streamlit 기반 간단 UI를 담고 있습니다. 로컬에서 빠르게 실행하려면 아래 지침을 따르세요.

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
streamlit run streamlit_app.py
```

앱 상단의 `Backend Base URL` 입력란은 기본값으로 `http://localhost:8000`을 사용합니다. 백엔드가 다른 주소/포트에서 동작하면 해당 값을 변경하세요.

## 백엔드(개발) 실행 예시

```bash
# 프로젝트 루트에서
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 추가 개선 제안

- 결과 시각화(차트), 파일 업로드(재무제표), 인증(간단한 토큰 입력) 등을 추가할 수 있습니다.
