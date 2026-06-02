from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from backend.common.contracts import build_agent_output, elapsed_ms
from backend.common.logging import request_id_context
from backend.common.providers import (
    NewsCollectionProvider,
    ToolNewsCollectionProvider,
)
from backend.common.tool_runtime import (
    execute_tool_step,
    serialize_tool_runs,
    summarize_tool_runs,
)
from backend.tools.news import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_ARTICLES,
    DEFAULT_SUMMARY_MODEL,
    execute_news_pipeline,
)
from backend.tools.prompts.news import NEWS_COLLECTOR_PROMPT

logger = logging.getLogger(__name__)


class NewsCollectorAgent:
    """대상 기업 뉴스 수집 전용 에이전트."""

    name = "news_collector"

    def __init__(self, provider: NewsCollectionProvider | None = None) -> None:
        self._provider = provider or ToolNewsCollectionProvider()

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """대상 기업 뉴스 수집 파이프라인을 실행한다."""
        started_at = perf_counter()
        request_id = payload.get("request_id")
        with request_id_context(request_id):
            company_name = payload.get("company_name")
            lookback_days = int(payload.get("lookback_days", DEFAULT_LOOKBACK_DAYS))
            max_articles = int(payload.get("max_articles", DEFAULT_MAX_ARTICLES))
            company_limit = payload.get("company_limit")
            summarize = bool(payload.get("summarize", True))
            model_name = str(payload.get("model_name", DEFAULT_SUMMARY_MODEL))
            database_url = payload.get("database_url")
            show_progress = bool(payload.get("show_progress", True))

            logger.info(
                (
                    "news_collector_started lookback_days=%s "
                    "max_articles=%s company_limit=%s summarize=%s model_name=%s"
                ),
                lookback_days,
                max_articles,
                company_limit,
                summarize,
                model_name,
            )

            news_result, pipeline_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="execute_news_pipeline",
                request_id=request_id,
                company_name=company_name,
                runner=lambda: self._provider.execute_news_pipeline(
                    database_url=database_url,
                    lookback_days=lookback_days,
                    max_articles=max_articles,
                    summarize=summarize,
                    model_name=model_name,
                    company_limit=company_limit,
                    show_progress=show_progress,
                    company_name=payload.get("company_name"),
                    corp_name=payload.get("corp_name"),
                    stock_code=payload.get("stock_code"),
                ),
                fallback_factory=_default_news_result,
                validate_dict=True,
            )
            tool_runs = [pipeline_run]
            fallback_used, tool_errors = summarize_tool_runs(tool_runs)

            logger.info(
                (
                    "news_collector_finished company_name=%s status=%s "
                    "company_count=%s article_count=%s inserted_count=%s "
                    "updated_count=%s tool_error_count=%s"
                ),
                company_name,
                news_result.get("status"),
                news_result.get("company_count"),
                news_result.get("article_count"),
                news_result.get("inserted_count"),
                news_result.get("updated_count"),
                len(tool_errors),
            )

            agent_status = "success"
            agent_error_code = "OK"
            pipeline_status = str(news_result.get("status", "success"))
            if pipeline_status not in {"success", "ok"} or fallback_used:
                agent_status = "partial"
                agent_error_code = "NEWS_PIPELINE_DEGRADED"

            return build_agent_output(
                {
                    "news_data": news_result.get("collected_news_data", []),
                    "news_result": news_result,
                    "news_collector_config": {
                        "lookback_days": lookback_days,
                        "max_articles": max_articles,
                        "company_limit": company_limit,
                        "summarize": summarize,
                        "model_name": model_name,
                        "prompt": NEWS_COLLECTOR_PROMPT,
                    },
                    "news_tool_runs": serialize_tool_runs(tool_runs),
                    "news_tool_errors": tool_errors,
                },
                status=agent_status,
                error_code=agent_error_code,
                fallback_used=fallback_used,
                latency_ms=elapsed_ms(started_at),
            )


def news_collection_node(state: dict[str, Any]) -> dict[str, Any]:
    """기존 노드 호출 스타일 호환용 래퍼."""
    pipeline_result = execute_news_pipeline(
        database_url=state.get("database_url"),
        lookback_days=int(state.get("lookback_days", DEFAULT_LOOKBACK_DAYS)),
        max_articles=int(state.get("max_articles", DEFAULT_MAX_ARTICLES)),
        summarize=bool(state.get("summarize", True)),
        model_name=str(state.get("model_name", DEFAULT_SUMMARY_MODEL)),
        company_limit=state.get("company_limit"),
        show_progress=bool(state.get("show_progress", True)),
        company_name=state.get("company_name"),
        corp_name=state.get("corp_name"),
        stock_code=state.get("stock_code"),
    )
    return {
        "news_data": pipeline_result.get("collected_news_data", []),
        "news_result": pipeline_result,
    }


def _default_news_result() -> dict[str, Any]:
    return {
        "status": "error",
        "company_count": 0,
        "article_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "collected_news_data": [],
    }
