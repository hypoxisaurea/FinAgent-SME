# MultiModal Document Agent

PDF 공시자료에서 텍스트와 차트 이미지를 추출하는 멀티모달 문서 에이전트입니다.

이 README는 새 팀원이 `backend/agents/multimodal_document` 에이전트를 바로 실행할 수 있도록 구성되어 있습니다.

## 1. 개요

- 에이전트 이름: `multimodal_document`
- 역할: PDF에서 텍스트를 추출하고 이미지 객체를 PNG 파일로 저장
- 주요 입력: `pdf_path`, `output_dir`
- 주요 출력: `texts`, `chart_images`, `page_count`

## 2. 사전 준비

### 2.1 환경 설정

```bash
cd /Users/princess1004/Desktop/MY/Projects/FinAgent-SME
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows에서는:

```bash
.\.venv\Scripts\activate
```

### 2.2 필수 패키지

- `pdfplumber`
- `fastapi`, `pydantic`, `requests` 등은 이미 `backend/requirements.txt`에 포함되어 있습니다.

## 3. 코드 구조

- `agent.py`: `MultiModalDocumentAgent` 클래스
  - `run(payload)`가 내부 작업을 순차 실행합니다.
  - `_build_context`에서 `pdf_path` 유효성을 검증하고 `output_dir`를 생성합니다.
- `processor.py`: PDF 텍스트/이미지 추출 로직
  - `extract_pdf_text(pdf_path)`
  - `extract_pdf_chart_images(pdf_path, output_dir)`
- `dart.py`: DART API 유틸리티 (이 에이전트 실행에는 직접 필요하지 않음)
- `result/`: 샘플 결과 파일

## 4. 직접 실행 방법

프로젝트 루트에서 `PYTHONPATH=backend`를 설정하고 호출합니다.

```bash
cd /Users/princess1004/Desktop/MY/Projects/FinAgent-SME
PYTHONPATH=backend python - <<'PY'
import asyncio
from agents.multimodal_document import MultiModalDocumentAgent

agent = MultiModalDocumentAgent()
payload = {
    "pdf_path": "/path/to/your/document.pdf",
    "output_dir": "/tmp/multimodal_document",
}
result = asyncio.run(agent.run(payload))
print(result)
PY
```

### 옵션 설명

- `pdf_path`: 분석할 PDF 파일 경로
- `output_dir`: PNG 이미지 파일을 저장할 디렉터리
  - 미지정 시 `MultiModalDocumentAgent` 내부에서 기본값으로 `/tmp/multimodal_document`를 사용합니다.

## 4.1 DART 다운로드 스크립트 실행 예시

`backend/agents/multimodal_document/dart.py`는 DART Open API에서 XML 공시 자료를 다운로드하는 별도 유틸 스크립트입니다.

- 단일 기업 처리:

```bash
cd /Users/princess1004/Desktop/MY/Projects/FinAgent-SME/backend/agents/multimodal_document
python dart.py --corp-code 01107665 --output-dir result
```

- CSV 기반 다수 기업 처리:

```bash
cd /Users/princess1004/Desktop/MY/Projects/FinAgent-SME/backend/agents/multimodal_document
python dart.py --input-csv ../collector/soyeon/sme_list.csv --output-dir result
```

`OPEN_DART_API_KEY`는 환경 변수 또는 `.env` 파일에 설정되어 있어야 합니다.

## 5. 출력 예시

`run()` 결과는 다음 필드를 포함합니다:

- `name`: `multimodal_document`
- `pdf_path`: 처리한 PDF 경로
- `output_dir`: 이미지 출력 디렉터리
- `texts`: 각 페이지에서 추출한 텍스트 문자열 리스트
- `chart_images`: 저장된 PNG 이미지 경로 리스트
- `page_count`: 추출한 페이지 수

## 6. 오케스트레이터 통합 사용

이 에이전트는 기존 워크플로우에 `extra_payload`로 전달할 수 있습니다.

```bash
cd /Users/princess1004/Desktop/MY/Projects/FinAgent-SME
PYTHONPATH=backend python - <<'PY'
import asyncio
from agents.orchestrator import run_credit_workflow

result = asyncio.run(
    run_credit_workflow(
        "My Company",
        extra_payload={"pdf_path": "/path/to/your/document.pdf"},
    )
)
print(result)
PY
```

- `run_credit_workflow` 내부에서 이 에이전트가 포함된 경우 `pdf_path`가 자동으로 전달됩니다.

## 7. 예외 및 주의 사항

- `pdf_path`가 없으면 `ValueError`가 발생합니다.
- PDF 파일이 존재하지 않으면 `FileNotFoundError`가 발생합니다.
- `output_dir`는 자동으로 생성됩니다.
- `pdfplumber`가 설치되지 않았으면 `RuntimeError`가 발생합니다.

## 8. 추가 참고

- `backend/agents/multimodal_document/agent.py`에서 `MultiModalDocumentAgent`는 두 단계 작업(`extract_text`, `extract_chart_images`)을 순차 실행합니다.
- `backend/agents/multimodal_document/processor.py`는 PDF 문서에서 텍스트와 이미지 정보를 분리해 추출합니다.
