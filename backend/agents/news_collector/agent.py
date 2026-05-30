from __future__ import annotations

import logging
from typing import Any

from agents.news_collector.prompts import NEWS_COLLECTOR_PROMPT
from agents.news_collector.tools import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_ARTICLES,
    DEFAULT_SUMMARY_MODEL,
    execute_news_pipeline,
)

logger = logging.getLogger(__name__)


class NewsCollectorAgent:
    """대상 기업 뉴스 수집 전용 에이전트."""

    name = "news_collector"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """대상 기업 뉴스 수집 파이프라인을 실행한다."""
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

        news_result = execute_news_pipeline(
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
        )

        logger.info(
            (
                "news_collector_finished status=%s company_count=%s "
                "article_count=%s inserted_count=%s updated_count=%s"
            ),
            news_result.get("status"),
            news_result.get("company_count"),
            news_result.get("article_count"),
            news_result.get("inserted_count"),
            news_result.get("updated_count"),
        )

        return {
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
        }


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
