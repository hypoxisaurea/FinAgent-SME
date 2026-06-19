# AGENTS.md

## 프로젝트 개요

- Product Name: FinAgent-SME
- Product Description: B2B 거래 리스크 심사 Multi-Agent System
- Target User: 은행/금융기관 심사 담당자
- Main Goal: 더 빠르고 정확한 대출 심사, 리스크 관리 강화, 효율적인 의사 결정
- 언어: Python
- 프레임워크: FastAPI, Pydantic
- 런타임: Python 3.13+

## 코드 규칙

- 함수명: snake_case
- 클래스명: PascalCase
- 한 함수는 하나의 역할만 수행한다
- 타입 힌트 필수
- 공개 API/서비스 레이어 함수에는 docstring 작성
- import 정렬 및 규칙은 ruff 기준을 따른다
- 상대 import 금지 (절대 import 사용)

## 절대 금지

- `print()` 사용 금지 → `logger.info()` 사용
- 직접 DB 쿼리 금지 → 반드시 서비스 레이어 경유
- 로그에 민감정보(주민번호, 계좌, 토큰, 키) 기록 금지

## 로깅 규칙

- 각 모듈에서 `logger = logging.getLogger(__name__)` 사용
- 예외는 삼키지 말고 로깅 후 명시적으로 처리/재전파
- 운영 추적이 필요한 이벤트(워크플로우 시작/종료, 실패)는 구조화된 메시지로 기록

## PR 규칙

- 커밋 메시지: `feat:`, `fix:`, `refactor:` 접두사 사용
- PR 하나에 하나의 변경만
- 테스트 없는 PR은 올리지 않는다
- PR 전 체크: lint + test 통과 필수
- 코드 스타일 수정과 기능 변경은 가능하면 분리

## 테스트

- 테스트 파일 위치: `tests/` 디렉토리
- 실행 명령: `.venv/bin/pytest -o cache_dir=.cache/pytest tests/`
- 새 기능에는 반드시 테스트 추가
- 버그 수정 시 회귀 테스트 추가
- 외부 API 의존 로직은 mocking 또는 fixture로 고립 테스트

## 실행 명령

- 모든 Python 실행/검증 명령은 프로젝트 루트에서 `.venv/bin/...` 사용
- Backend 실행: `.venv/bin/python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000`
- Frontend 실행: `.venv/bin/python -m streamlit run frontend/main.py --server.address 0.0.0.0 --server.port 8501`

## 품질 게이트

- Backend lint: `.venv/bin/ruff check backend`
- Frontend lint: `.venv/bin/ruff check frontend`
- 테스트: `.venv/bin/pytest -o cache_dir=.cache/pytest tests/`
- 병합 전 최소 검증: `.venv/bin/ruff check backend frontend tests` + `.venv/bin/pytest -o cache_dir=.cache/pytest tests/`

## API/에러 처리 규칙

- 입력 검증 오류는 4xx, 서버 내부 오류는 5xx로 구분
- FastAPI 스키마(Pydantic)로 입출력 계약을 명시
- 에러 응답 형식은 일관되게 유지 (`code`, `message`, `detail`)

## 문서 기준 (Source of Truth)

- 네이밍 규칙: `docs/conventions/naming.md`
- 에러 처리 규칙: `docs/conventions/error-handling.md`
- 테스트 규칙: `docs/conventions/testing.md`
- 도메인 워크플로우: `docs/domain/workflows.md`
