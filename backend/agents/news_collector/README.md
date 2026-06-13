# News Collector Agent

## 역할

`NewsCollectorAgent`는 기업 뉴스를 수집하고, 필요 시 요약한 뒤, DB와 오케스트레이터 downstream에 동시에 전달합니다.

## 현재 입력

- `company_name`
- `corp_name`
- `stock_code`
- `lookback_days` (default `90`)
- `max_articles` (default `5`)
- `company_limit`
- `summarize` (default `True`)
- `model_name` (default `gpt-4o-mini`)
- `show_progress`
- `database_url`

오케스트레이터 단건 실행에서는 주로 `company_name`, `corp_name`, `stock_code`를 사용합니다.

## 현재 출력

- `news_result`
- `news_data`
- `news_collector_config`
- `news_tool_runs`
- `news_tool_errors`

공통 메타데이터:

- `status`
- `error_code`
- `fallback_used`
- `latency_ms`

## DB 적재

테이블: `daum_news_articles`

대표 컬럼:

- `stock_code`
- `corp_name`
- `news_title`
- `press_name`
- `published_at`
- `url`
- `content`
- `content_type`
- `created_at`

유니크 제약:

- `(stock_code, url)`

## 오케스트레이터 연동

- agent 이름: `news_collector`
- 시작 분석 노드로 실행됩니다
- `RiskEventAgent`가 이 agent의 `news_data`를 downstream 입력으로 사용합니다

`news_data[*]`는 최소한 아래 키를 제공하는 것을 목표로 합니다.

- `title`
- `content`
- `published_at`
- `url`

## 상태 규칙

- 파이프라인 성공 시 `status=success`
- 일부 수집/요약 단계가 degraded 되면 `status=partial`
- 도구 오류 정보는 `news_tool_errors`에 보존됩니다

## 의존성

- Daum News
- PostgreSQL
- OpenRouter 요약 사용 시 `OPEN_ROUTER_API_KEY`

## 테스트

```bash
.venv/bin/pytest tests/integration/test_agent_tool_fallbacks.py -q
.venv/bin/pytest tests/integration/test_workflow_orchestrator.py -q
```
