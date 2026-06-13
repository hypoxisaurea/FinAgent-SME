# Naming Conventions

## 공통 원칙

- 의미가 분명한 이름을 사용한다.
- 같은 개념에는 같은 이름을 유지한다.
- 불필요한 축약어를 피한다.

## Python

- 파일/모듈명: `snake_case.py`
- 함수/메서드명: `snake_case`
- 변수명: `snake_case`
- 클래스명: `PascalCase`
- 상수명: `UPPER_SNAKE_CASE`
- 비공개 멤버: `_leading_underscore`

예시:

- `run_credit_workflow`
- `WorkflowOrchestrator`
- `DEFAULT_AGENT_TIMEOUT_SECONDS`

## Agent 네이밍

- agent 클래스명: `<Domain><Role>Agent`
- agent 식별자 `name`: 소문자 `snake_case`
- 패키지 구조는 현재 `backend/agents/<agent_name>/agent.py`를 사용한다

예시:

- 클래스: `FinancialAnalystAgent`
- 식별자: `financial_analyst`
- 파일: `backend/agents/financial_analyst/agent.py`

## API / Schema 네이밍

- API path: 소문자 + 하이픈
- JSON key: `snake_case`
- Pydantic 모델명: `PascalCase`
- 상태 문자열: 소문자 문자열

현재 예시:

- `/api/v1/workflows/credit-assessment`
- `CreditAssessmentRequest`
- `success`, `partial`, `failed`, `not_target`

## 데이터 계층 네이밍

- repository 함수는 조회 기준이 드러나야 한다
- service 함수는 use-case 의도가 드러나야 한다

예시:

- `find_company_row_by_name`
- `get_financial_rows_by_corp_code`
- `execute_dart_pipeline`

## 프론트엔드 네이밍

현재 프론트엔드는 Streamlit 기반 Python 앱이다.

- 화면 함수명: `render`
- 상태 키: `snake_case`
- 파일명: 역할 중심 `snake_case.py`

예시:

- `search.py`
- `report.py`
- `last_result`

## 금지 규칙

- 동일 맥락에서 `corpNm`, `corp_name` 같은 혼용 금지
- 의미 없는 접미사 `temp`, `new`, `data` 남용 금지
- 현재 존재하지 않는 상태값을 문서/코드에서 임의로 추가하지 않는다
