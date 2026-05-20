# Backend

FinAgent-SME의 백엔드는 FastAPI API 레이어와 여러 분석/수집 에이전트 모듈로 구성됩니다. 이 문서는 `backend` 디렉터리에서 필요한 실행 방법, 구조, 에이전트 역할을 한곳에 모아 둔 단일 안내서입니다.

## 개요

- API 프레임워크: FastAPI
- 주요 역할: 기업 심사 워크플로우 오케스트레이션, 재무/산업 분석, 문서 처리, 데이터 수집
- Python 버전 기준: 3.11+
- 의존성 설치 파일: 프로젝트 루트 `requirements.txt`

## 빠른 시작

프로젝트 루트에서 실행합니다.

```bash
cd /Users/princess1004/Desktop/MY/Projects/FinAgent-SME
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
./setup.sh db-up
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

백엔드와 프론트, PostgreSQL을 함께 올리려면 프로젝트 루트에서 아래 명령을 사용할 수 있습니다.

```bash
./setup.sh
```

PostgreSQL이 필요한 에이전트를 실행할 때 자주 쓰는 명령:

```bash
./setup.sh db-up
./setup.sh db-status
./setup.sh db-down
```

주요 확인 경로:

- `GET /` -> 서비스 메타 정보
- `GET /api/health` -> 헬스체크
- `POST /api/v1/workflows/credit-assessment` -> 심사 워크플로우 진입점
- `POST /api/v1/workflows/orchestrator` -> 프론트 검색 버튼이 호출하는 오케스트레이터 진입점
- `GET /docs` -> Swagger UI

## 환경 변수

기능별로 아래 환경 변수가 사용됩니다.

```env
OPENAI_API_KEY=...
OPEN_DART_API_KEY=...
ECOS_API_KEY=...
KOSIS_API_KEY=...
```

- `OPENAI_API_KEY`: `financial_analyst`, `industry_analyst` LLM 호출에 사용
- `OPEN_DART_API_KEY`: DART 재무/기업 정보 조회에 사용
- `ECOS_API_KEY`: 한국은행 ECOS 거시지표 조회에 사용
- `KOSIS_API_KEY`: 통계청 KOSIS 업황 데이터 조회에 사용

`backend/.env` 파일은 `backend/config.py`와 각 에이전트 모듈에서 함께 참조합니다. 기존에 `backend/agents/.env`를 사용 중이었다면 같은 값을 `backend/.env`로 옮겨두면 됩니다. PostgreSQL용 Docker Compose는 `backend/docker-compose.yml`에 있고, 루트 `setup.sh`가 이 파일을 기준으로 DB를 실행합니다.

## 디렉터리 구조

```text
backend/
├── main.py                      # FastAPI 앱 엔트리포인트
├── config.py                    # 환경 설정
├── api/                         # 라우터
├── schemas/                     # 요청/응답 및 상태 스키마
├── utils/                       # 공통 유틸리티
└── agents/
    ├── collector/               # DART 중소기업 후보군 수집 스크립트
    ├── multimodal_document/     # PDF 텍스트/이미지 추출 에이전트
    ├── financial_analyst/       # 재무비율/Altman Z' 분석 에이전트
    ├── industry_analyst/        # 산업 평균/업황/거시지표 분석 에이전트
    ├── risk_event/              # 리스크 이벤트 탐지 모듈
    ├── decision/                # 의사결정 관련 모듈
    ├── report/                  # 보고서 생성 관련 모듈
    └── orchestrator/            # 다중 에이전트 워크플로우 조합
```

## API 구조

- `backend/main.py`: FastAPI 앱 생성 및 CORS 설정
- `backend/api/routes/health.py`: `/api/health`
- `backend/api/routes/workflows.py`: `/api/v1/workflows/credit-assessment`
- `backend/agents/orchestrator/orchestrator.py`: 워크플로우 실행 로직

현재 워크플로우 진입점은 `run_credit_workflow()`입니다. 다만 `collector`는 현재 독립 수집 스크립트 성격이 강하므로, 오케스트레이터 연동 시에는 실제 모듈 경로와 구현 상태를 함께 확인하는 것을 권장합니다.

## 에이전트 정리

### 1. Collector

DART(OpenDART)에서 중소기업 후보군과 기초 재무 데이터를 수집하는 1차 추출 스크립트입니다. 전체 파이프라인에 연결된 패키지형 에이전트라기보다, 후속 분석용 입력 데이터를 만드는 독립 도구에 가깝습니다.

- 위치: `backend/agents/collector/tools.py`
- 주요 산출물:
  - `sme_list.csv`
  - `financial_features.csv`
  - `financial_error_logs.csv`
- 기본 필터:
  - 자산총계 5,000억 이하
  - 최근 3개년 평균 매출 1,000억 이하
- 기본값:
  - 사업연도 `2024`
  - 보고서 코드 `11011`

실행 예시:

```bash
cd /Users/princess1004/Desktop/MY/Projects/FinAgent-SME
PYTHONPATH=backend python - <<'PY'
from agents.collector.tools import execute_dart_pipeline, run_self_tests

run_self_tests()
result = execute_dart_pipeline(
    year=2024,
    sample_size=100,
    skip_db_save=False,
    output_dir="temp_result",
)
print(result)
PY
```

주요 옵션:

- `year`
- `sample_size`
- `skip_db_save`
- `output_dir`

### 2. MultiModal Document Agent

PDF 공시자료에서 텍스트와 차트 이미지를 추출하는 문서 처리 에이전트입니다.

- 위치: `backend/agents/multimodal_document`
- 주요 입력: `pdf_path`, `output_dir`
- 주요 출력: `texts`, `chart_images`, `page_count`
- 핵심 파일:
  - `agent.py`
  - `processor.py`
  - `dart.py`

직접 실행 예시:

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
PY
```

주의 사항:

- `pdf_path`가 없으면 `ValueError`
- 파일이 없으면 `FileNotFoundError`
- `output_dir`는 자동 생성

### 3. Financial Analyst Agent

DART 재무제표를 기반으로 기업의 정량 재무 리스크를 분석하는 에이전트입니다. 산업 비교나 뉴스 해석이 아니라 재무 수치 계산과 이상 징후 탐지에 집중합니다.

- 위치: `backend/agents/financial_analyst`
- LLM: `ChatOpenAI(model="gpt-4.1-nano")`
- 주요 도구:
  - `get_financial_statements(corp_code, year)`
  - `calc_financial_ratios(fs)`
  - `calc_altman_z_prime(fs)`
  - `trend_analysis(corp_code, years)`

주요 산출 항목:

- 부채비율
- 유동비율
- ROA
- 영업이익률
- 이자보상배율
- 영업현금흐름 관련 비율
- Altman Z'-Score
- 최근 3개년 추세 플래그

도구 사용 예시:

```python
from backend_env import load_backend_env
from agents.financial_analyst.financial_tools import (
    calc_altman_z_prime,
    calc_financial_ratios,
    get_financial_statements,
    trend_analysis,
)

load_backend_env()

fs = get_financial_statements.invoke({"corp_code": "01074862", "year": 2023})
ratios = calc_financial_ratios.invoke({"fs": fs})
z_score = calc_altman_z_prime.invoke({"fs": fs})
trend = trend_analysis.invoke({"corp_code": "01074862", "years": [2021, 2022, 2023]})
```

에이전트 호출 예시:

```python
from backend_env import load_backend_env
from agents.financial_analyst import financial_agent

load_backend_env()

result = financial_agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "corp_code 01074862, 2023년 재무 분석해줘",
            }
        ]
    }
)
```

### 4. Industry Analyst Agent

산업 평균 재무비율, 업황 신호, 거시지표를 분석하는 에이전트입니다. 개별 기업의 재무 계산은 `financial_analyst`가 담당하고, 이 에이전트는 산업 수준의 맥락 해석에 집중합니다.

- 위치: `backend/agents/industry_analyst`
- LLM: `ChatOpenAI(model="gpt-4.1-nano")`
- 데이터 소스:
  - DART Open API
  - 한국은행 ECOS Open API
  - KOSIS Open API
  - 로컬 CSV `data/asset_ratio.csv`, `data/profit_ratio.csv`
- 주요 도구:
  - `map_corp_to_ksic(corp_code)`
  - `get_industry_avg_ratios(ksic_code, year)`
  - `compare_to_industry(company_ratios, industry_avg)`
  - `get_industry_outlook(ksic_code)`
  - `get_macro_indicators()`

주요 판단 항목:

- KSIC 업종 매핑
- 중소기업 산업 평균 대비 상대 비교
- 생산/재고/출하 기반 업황 등급
- 기준금리, 원달러 환율, 금리 추세

도구 사용 예시:

```python
from backend_env import load_backend_env
from agents.industry_analyst.industry_tools import (
    compare_to_industry,
    get_industry_avg_ratios,
    get_industry_outlook,
    get_macro_indicators,
    map_corp_to_ksic,
)

load_backend_env()

ksic = map_corp_to_ksic.invoke({"corp_code": "01074862"})
avg = get_industry_avg_ratios.invoke({"ksic_code": ksic, "year": 2023})
outlook = get_industry_outlook.invoke({"ksic_code": "C 제조업"})
macro = get_macro_indicators.invoke({})
comparison = compare_to_industry.invoke(
    {
        "company_ratios": {
            "debt_ratio": 0.94,
            "op_margin": 0.13,
            "current_ratio": 0.57,
        },
        "industry_avg": avg,
    }
)
```

에이전트 호출 예시:

```python
from backend_env import load_backend_env
from agents.industry_analyst import industry_agent

load_backend_env()

result = industry_agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": "corp_code 01074862, 2023년 산업 분석해줘",
            }
        ]
    }
)
```

참고:

- 일부 업종은 산업평균 CSV가 없어 `N/A`를 반환할 수 있습니다.
- 단독 실행 시 `compare_to_industry`는 입력 비율이 없으면 `n/a`가 나올 수 있습니다.

## 품질 확인

프로젝트 루트에서 아래 명령으로 최소 검증을 수행합니다.

```bash
ruff check backend
pytest tests/
```

프론트엔드까지 함께 확인하려면:

```bash
cd frontend
npm run lint
```

## 운영 메모

- 민감정보는 로그에 남기지 않습니다.
- 공개 서비스 레이어와 API 입출력은 Pydantic 스키마 기준으로 유지합니다.
- 입력 검증 오류는 4xx, 내부 오류는 5xx로 구분합니다.
- 문서 기준은 `docs/conventions/`와 `docs/domain/workflows.md`를 우선합니다.
