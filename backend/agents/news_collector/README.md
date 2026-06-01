# News Collector Agent

`backend/agents/news_collector`는 `sme_list`에 있는 기업을 기준으로 다음 금융 뉴스를 수집하고, 기사 본문을 요약한 뒤, DB와 오케스트레이터 downstream에 동시에 전달하는 에이전트입니다.

## 역할

- DB의 `sme_list` 테이블에서 `stock_code`, `corp_name`을 조회합니다.
- 다음 금융 뉴스 목록 API를 호출해 최근 `lookback_days` 기간의 기사를 수집합니다.
- 한 번의 실행에서 기업별 기사 수를 기본 `5`건(`max_articles`)으로 제한합니다.
- 기사 URL에 접속해 본문을 추출합니다.
- 필요 시 OpenAI로 기사 본문을 3문장 이내 감성 분석 친화형 요약으로 변환합니다.
- 결과를 `daum_news_articles` 테이블에 upsert 합니다.
- 오케스트레이터 실행 시 `risk_event`가 바로 사용할 수 있도록 `news_data`를 함께 반환합니다.

## 폴더 구성

- [agent.py](/Users/suminkang/Desktop/2026/pocat/official_git/FinAgent-SME/backend/agents/news_collector/agent.py): 오케스트레이터용 에이전트 진입점
- [tools.py](/Users/suminkang/Desktop/2026/pocat/official_git/FinAgent-SME/backend/agents/news_collector/tools.py): DB, 크롤링, 본문 추출, 요약, 적재 로직
- [prompts.py](/Users/suminkang/Desktop/2026/pocat/official_git/FinAgent-SME/backend/agents/news_collector/prompts.py): LLM 요약 프롬프트

## 입력과 출력

`NewsCollectorAgent.run(payload)`는 아래 값을 읽습니다.

- `database_url`: 명시적 DB 연결 문자열
- `lookback_days`: 뉴스 조회 기간, 기본값 `90`
- `max_articles`: 기업별 최대 기사 수, 기본값 `5`
- `company_limit`: DB에서 읽을 SME 수 제한
- `summarize`: 기사 내용을 요약해서 저장할지 여부, 기본값 `True`
- `model_name`: 요약 모델명, 기본값 `gpt-4o-mini`
- `show_progress`: tqdm 출력 여부
- `company_name`, `corp_name`, `stock_code`: 오케스트레이터 단건 실행 시 대상 기업 필터

반환값에는 아래 키가 포함됩니다.

- `news_result`: 전체 수집 통계와 실행 결과
- `news_data`: `risk_event`가 바로 사용할 기사 목록
- `news_collector_config`: 실행 설정과 프롬프트

## DB 적재 구조

테이블명은 `daum_news_articles`입니다.

- `stock_code`
- `corp_name`
- `news_title`
- `press_name`
- `published_at`
- `url`
- `content`
- `content_type`
- `created_at`

중복 기준은 `(stock_code, url)` 유니크 제약입니다. 이미 존재하는 기사는 제목, 본문, 발행시각, `content_type` 등을 update 합니다.

## Orchestrator 연동

오케스트레이터는 `NewsCollectorAgent`를 병렬 분석 단계에 배치하고, 이후 `risk_event`를 `news_collector` 뒤에 연결합니다.

현재 `news_collector`는 오케스트레이터 문맥에서 다음을 보장합니다.

- `company_name` 또는 `corp_name`, `stock_code`가 전달되면 해당 기업 뉴스만 필터링합니다.
- `risk_event`가 기대하는 `news_data` 형식으로 결과를 반환합니다.
- `news_data[*]`는 최소한 `title`, `content`, `published_at`, `url`을 포함합니다.

## Risk Event 연동

`risk_event`는 `payload.get("news_data", [])`를 읽어 감성 분석과 키워드 탐지를 수행합니다. 따라서 `news_collector`는 DB 적재용 스키마와 별도로 downstream 호환용 `news_data`를 함께 반환합니다.

요약 저장을 켠 경우:

- DB의 `content`에는 요약문이 저장됩니다.
- `risk_event`에도 동일한 요약문이 `news_data[*].content`로 전달됩니다.

요약 저장을 끈 경우:

- DB와 `risk_event` 모두 기사 본문 원문을 사용합니다.

## 환경 변수

다음 값 중 하나가 필요합니다.

```env
DATABASE_URL=postgresql+psycopg2://...
```

또는

```env
POSTGRES_HOST=...
POSTGRES_PORT=5432
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
```

OpenAI 요약 사용 시:

```env
OPEN_AI_API_KEY=...
```

레거시 호환으로 `OPENAI_API_KEY`, `OPEN_API_KEY`도 읽습니다.

## 테스트 방법

### 1. import 및 오케스트레이터 연결 확인

프로젝트 루트에서:

```bash
.venv/bin/python -c "import sys; sys.path.insert(0, 'backend'); from agents.news_collector import NewsCollectorAgent; print(NewsCollectorAgent.name)"
```

정상이라면 `news_collector`가 출력됩니다.

### 2. 기존 오케스트레이터 회귀 테스트

```bash
.venv/bin/pytest -q tests/integration/test_workflow_orchestrator.py
```

이 테스트는 `news_collector` 출력이 downstream 문맥에 합쳐져 `risk_event`로 전달되는 계약을 검증합니다.

### 3. 단건 스모크 테스트

실제 DB와 API 키가 준비되어 있다면:

```bash
cd backend
../.venv/bin/python - <<'PY'
import asyncio
from agents.news_collector import NewsCollectorAgent

async def main():
    agent = NewsCollectorAgent()
    result = await agent.run({
        "company_name": "테스트기업명",
        "lookback_days": 30,
        "company_limit": 50,
        "summarize": True,
        "show_progress": False,
    })
    print("news_data:", len(result.get("news_data", [])))
    print("news_result:", result.get("news_result"))

asyncio.run(main())
PY
```

확인 포인트:

- `news_result["status"] == "success"`
- `news_result["inserted_count"] + news_result["updated_count"] >= 0`
- `news_data`가 비어 있지 않으면 `risk_event`에서 바로 사용 가능
- DB의 `daum_news_articles`에 레코드가 적재되었는지 확인

### 4. DB 적재 확인 SQL

```sql
SELECT stock_code, corp_name, news_title, content_type, published_at, url
FROM daum_news_articles
ORDER BY created_at DESC
LIMIT 20;
```

### 5. Risk Event 직접 연동 확인

```bash
cd backend
../.venv/bin/python - <<'PY'
import asyncio
from agents.news_collector import NewsCollectorAgent
from agents.risk_event import RiskEventAgent

async def main():
    news_agent = NewsCollectorAgent()
    risk_agent = RiskEventAgent()

    news_output = await news_agent.run({
        "company_name": "테스트기업명",
        "summarize": True,
        "show_progress": False,
    })

    risk_output = await risk_agent.run({
        "company_name": "테스트기업명",
        "corp_code": "00000000",
        "news_data": news_output.get("news_data", []),
        "disclosure_data": [],
        "court_data": [],
    })

    print("risk level:", risk_output.get("overall_risk_level"))
    print("event count:", risk_output.get("total_event_count"))

asyncio.run(main())
PY
```

이 단계는 `news_collector -> risk_event` 데이터 형식이 맞는지 빠르게 확인하는 용도입니다.
