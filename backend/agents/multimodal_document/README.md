# Multimodal Document Agent

## 역할

`MultiModalDocumentAgent`는 PDF 공시 자료에서 텍스트와 차트 이미지를 추출하는 선택형 문서 분석 agent입니다.

## 현재 입력

- `pdf_path` (required)
- `output_dir` (optional, 기본 `/tmp/multimodal_document`)

## 현재 출력

- `name`
- `pdf_path`
- `output_dir`
- `texts`
- `chart_images`
- `page_count`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## 내부 처리 순서

1. 입력 경로를 검증하고 출력 디렉터리를 준비합니다.
2. `extract_pdf_text()`로 페이지별 텍스트를 추출합니다.
3. `extract_pdf_chart_images()`로 차트 이미지를 저장합니다.

## 상태 규칙

- 모든 작업이 정상 완료되면 `status=success`
- `pdf_path`가 없으면 `ValueError`
- 파일이 없으면 `FileNotFoundError`
- 내부 task가 dict를 반환하지 않으면 `TypeError`

## 오케스트레이터 연동

- agent 이름: `multimodal_document`
- 공개 API 기본 흐름에는 포함되지 않습니다.
- 내부 payload에 `pdf_path`가 있을 때만 병렬 시작 노드에 추가됩니다.

## 테스트

현재 저장소에는 이 agent 전용 pytest 문서는 아직 없습니다. 문서 경로를 공개 UI/API로 노출하기 전에 회귀 테스트를 추가하는 것이 좋습니다.
