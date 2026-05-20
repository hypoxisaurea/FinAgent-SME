from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agents.base import Agent

from agents.collector.prompts import COLLECTOR_AGENT_PROMPT

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CollectorTask:
    """수집원별 실행 단위."""

    source: str
    handler_name: str


class CollectorAgent(Agent):
    """다중 수집원을 조합해 기업 데이터를 수집하는 에이전트."""

    name = "collector"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """payload 설정을 바탕으로 수집 파이프라인을 순차 실행합니다."""
        config = _build_collector_config(payload)
        tasks = _build_tasks(config["sources"])

        logger.info(
            "collector_run_started year=%s sample_size=%s skip_db_save=%s output_dir=%s sources=%s",
            config["year"],
            config["sample_size"],
            config["skip_db_save"],
            config["output_dir"],
            config["sources"],
        )

        source_results: dict[str, dict[str, Any]] = {}
        for task in tasks:
            source_results[task.source] = _run_task(task, config)

        combined_result = _build_combined_result(source_results)

        logger.info("collector_run_finished status=%s sources=%s", combined_result["status"], config["sources"])

        return {
            "collector_result": combined_result,
            "collector_sources": source_results,
            "dart_result": source_results.get("dart"),
            "news_result": source_results.get("news"),
            "collector_config": {
                "year": config["year"],
                "sample_size": config["sample_size"],
                "skip_db_save": config["skip_db_save"],
                "output_dir": config["output_dir"],
                "sources": config["sources"],
                "prompt": COLLECTOR_AGENT_PROMPT,
            },
        }


def dart_collection_node(state: dict[str, Any]) -> dict[str, Any]:
    """기존 노드 스타일 호출을 유지하기 위한 동기 래퍼."""
    config = _build_collector_config(state)
    pipeline_result = _execute_dart_pipeline(config)
    return {
        "dart_result": {
            "status": pipeline_result.get("status", "success"),
            "sme_count": pipeline_result.get("sme_count", 0),
            "financial_data_count": pipeline_result.get("financial_data_count", 0),
            "stats": pipeline_result.get("stats", {}),
            "db_save_counts": pipeline_result.get("db_save_counts", {}),
        }
    }


def news_collection_node(state: dict[str, Any]) -> dict[str, Any]:
    """추후 뉴스 수집 노드를 직접 연결할 때 사용할 동기 래퍼."""
    config = _build_collector_config(state)
    pipeline_result = _execute_news_pipeline(config)
    return {"news_result": pipeline_result}


def _build_collector_config(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "year": int(payload.get("target_year", 2024)),
        "sample_size": payload.get("run_sample_size"),
        "skip_db_save": bool(payload.get("skip_db_save", False)),
        "output_dir": str(payload.get("output_dir", ".")),
        "sources": _normalize_sources(payload.get("collect_sources")),
        "company_name": payload.get("company_name"),
    }


def _normalize_sources(raw_sources: Any) -> list[str]:
    if raw_sources is None:
        return ["dart"]

    if isinstance(raw_sources, str):
        candidate_sources = [raw_sources]
    elif isinstance(raw_sources, list):
        candidate_sources = raw_sources
    else:
        raise TypeError("collect_sources는 문자열 또는 문자열 리스트여야 합니다.")

    normalized_sources: list[str] = []
    for source in candidate_sources:
        if not isinstance(source, str):
            raise TypeError("collect_sources 항목은 문자열이어야 합니다.")
        normalized_source = source.strip().lower()
        if not normalized_source:
            continue
        if normalized_source not in {"dart", "news"}:
            raise ValueError(f"지원하지 않는 collect source입니다: {source}")
        if normalized_source not in normalized_sources:
            normalized_sources.append(normalized_source)

    return normalized_sources or ["dart"]


def _build_tasks(sources: list[str]) -> list[CollectorTask]:
    handler_map = {
        "dart": "dart",
        "news": "news",
    }
    return [CollectorTask(source=source, handler_name=handler_map[source]) for source in sources]


def _run_task(task: CollectorTask, config: dict[str, Any]) -> dict[str, Any]:
    if task.handler_name == "dart":
        return _execute_dart_pipeline(config)
    if task.handler_name == "news":
        return _execute_news_pipeline(config)
    raise ValueError(f"지원하지 않는 collector task입니다: {task.handler_name}")


def _execute_dart_pipeline(config: dict[str, Any]) -> dict[str, Any]:
    # pandas/dart_fss 의존성을 실제 실행 시점까지 늦춰 import 오류 전파를 명확히 한다.
    from agents.collector.tools import execute_dart_pipeline

    return execute_dart_pipeline(
        year=config["year"],
        sample_size=config["sample_size"],
        skip_db_save=config["skip_db_save"],
        output_dir=config["output_dir"],
    )


def _execute_news_pipeline(config: dict[str, Any]) -> dict[str, Any]:
    from agents.collector.tools import execute_news_pipeline

    return execute_news_pipeline(
        company_name=config.get("company_name"),
        year=config["year"],
        output_dir=config["output_dir"],
    )


def _build_combined_result(source_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    statuses = [result.get("status", "unknown") for result in source_results.values()]
    success_statuses = {"success", "skipped"}
    ok_count = sum(status in success_statuses for status in statuses)

    if not statuses:
        status = "not_started"
    elif all(status == "not_configured" for status in statuses):
        status = "not_configured"
    elif ok_count == len(statuses):
        status = "success"
    elif ok_count == 0:
        status = "failed"
    else:
        status = "partial"

    return {
        "status": status,
        "sources": source_results,
        "requested_sources": list(source_results.keys()),
    }
