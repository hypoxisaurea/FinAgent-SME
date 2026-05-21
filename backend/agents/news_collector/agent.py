from __future__ import annotations

import logging
from typing import Any

from agents.base import Agent
from agents.news_collector.prompts import NEWS_COLLECTOR_PROMPT
from agents.news_collector.tools import execute_news_pipeline

logger = logging.getLogger(__name__)


class NewsCollectorAgent(Agent):
    """대상 기업 뉴스 수집 전용 에이전트."""

    name = "news_collector"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """대상 기업 뉴스 수집 파이프라인을 실행한다."""
        company_name = payload.get("company_name")
        year = int(payload.get("target_year", 2024))
        output_dir = str(payload.get("output_dir", "."))

        logger.info(
            "news_collector_started company_name=%s year=%s output_dir=%s",
            company_name,
            year,
            output_dir,
        )

        news_result = execute_news_pipeline(
            company_name=company_name,
            year=year,
            output_dir=output_dir,
        )
        news_items = news_result.get("items", [])

        logger.info(
            "news_collector_finished status=%s article_count=%s",
            news_result.get("status"),
            news_result.get("article_count", len(news_items)),
        )

        return {
            "news_result": news_result,
            "news_data": list(news_items),
            "news_collector_config": {
                "year": year,
                "output_dir": output_dir,
                "prompt": NEWS_COLLECTOR_PROMPT,
            },
        }


def news_collection_node(state: dict[str, Any]) -> dict[str, Any]:
    """기존 뉴스 수집 노드 호출을 유지하기 위한 래퍼."""
    year = int(state.get("target_year", 2024))
    output_dir = str(state.get("output_dir", "."))
    pipeline_result = execute_news_pipeline(
        company_name=state.get("company_name"),
        year=year,
        output_dir=output_dir,
    )
    return {"news_result": pipeline_result}
