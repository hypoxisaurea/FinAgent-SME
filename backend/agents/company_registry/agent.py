from __future__ import annotations

import logging
from typing import Any

from agents.base import Agent
from agents.company_registry.tools import execute_dart_pipeline

logger = logging.getLogger(__name__)


class CompanyRegistryBuilderAgent(Agent):
    """기업 마스터/재무 DB 구축 파이프라인을 실행하는 에이전트."""

    name = "company_registry_builder"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """DART 기반 기업 마스터와 재무 피처 데이터를 구축한다."""
        year = int(payload.get("target_year", 2024))
        sample_size = _parse_sample_size(payload.get("run_sample_size"))
        skip_db_save = bool(payload.get("skip_db_save", False))
        output_dir = str(payload.get("output_dir", "."))

        logger.info(
            (
                "company_registry_build_started year=%s sample_size=%s "
                "skip_db_save=%s output_dir=%s"
            ),
            year,
            sample_size,
            skip_db_save,
            output_dir,
        )

        result = execute_dart_pipeline(
            year=year,
            sample_size=sample_size,
            skip_db_save=skip_db_save,
            output_dir=output_dir,
        )

        logger.info(
            "company_registry_build_finished status=%s sme_count=%s",
            result.get("status"),
            result.get("sme_count"),
        )
        return {
            "company_registry_result": result,
            "dart_result": result,
        }


def dart_collection_node(state: dict[str, Any]) -> dict[str, Any]:
    """기존 DART 배치 수집 노드 호출을 유지하기 위한 래퍼."""
    year = int(state.get("target_year", 2024))
    sample_size = _parse_sample_size(state.get("run_sample_size"))
    skip_db_save = bool(state.get("skip_db_save", False))
    output_dir = str(state.get("output_dir", "."))
    pipeline_result = execute_dart_pipeline(
        year=year,
        sample_size=sample_size,
        skip_db_save=skip_db_save,
        output_dir=output_dir,
    )
    return {
        "dart_result": {
            "status": pipeline_result.get("status", "success"),
            "sme_count": pipeline_result.get("sme_count", 0),
            "financial_data_count": pipeline_result.get("financial_data_count", 0),
            "stats": pipeline_result.get("stats", {}),
            "db_save_counts": pipeline_result.get("db_save_counts", {}),
        }
    }


def _parse_sample_size(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
