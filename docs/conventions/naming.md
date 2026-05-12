# Naming Conventions

## 공통 원칙

- 의미가 명확한 이름을 사용한다.
- 축약어는 도메인 표준 약어만 허용한다.
- 한 이름은 하나의 책임/개념만 표현한다.

## Python (Backend)

- 파일/모듈명: `snake_case.py`
- 함수/메서드명: `snake_case`
- 변수명: `snake_case`
- 클래스명: `PascalCase`
- 상수명: `UPPER_SNAKE_CASE`
- 비공개 멤버: 접두사 `_` 사용

예시:
- `run_credit_workflow`
- `WorkflowOrchestrator`
- `DEFAULT_TIMEOUT_SECONDS`

## React (Frontend)

- 컴포넌트 파일명: `PascalCase.jsx` 또는 `PascalCase.tsx`
- 훅 함수명: `useSomething`
- 일반 유틸 함수명: `camelCase`
- CSS 클래스명: 프로젝트 전역 규칙을 따르되 일관성 유지

예시:
- `CreditSummaryCard.jsx`
- `useCreditDecision`
- `formatCurrency`

## Agent 네이밍 규칙

- Agent 클래스명: `<Domain><Role>Agent` (PascalCase)
- Agent 식별자(`name`): 소문자 `snake_case`
- Agent 모듈 파일명: `<domain>_agent.py`

예시:
- 클래스: `FinancialAnalystAgent`
- name: `financial_analyst`
- 파일: `financial_analyst_agent.py`

## API/스키마 네이밍

- API Path: 소문자 + 하이픈, 리소스 중심
  - 예: `/api/v1/workflows/credit-assessment`
- JSON 키: `snake_case`
- Pydantic 모델명: `PascalCase`
- enum 값: 소문자 문자열
  - 예: `success`, `partial`, `failed`, `not_configured`

## 금지 규칙

- 의미 없는 접두사/접미사(`data`, `temp`, `new`) 남용 금지
- 동일 컨텍스트에서 동음이의어 사용 금지
- 축약어가 섞인 비일관 네이밍 금지 (예: `compNm`, `company_name` 혼용)
