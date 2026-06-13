from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from backend.common.agent import Agent
from backend.common.contracts import build_agent_output, elapsed_ms
from backend.common.logging import request_id_context
from backend.common.providers import (
    IndustryDataProvider,
    ToolIndustryDataProvider,
)
from backend.common.tool_runtime import (
    execute_tool_step,
    serialize_tool_runs,
    summarize_tool_runs,
)
from backend.schemas.agent_contracts import (
    IndustryAnalystInput,
    IndustryAnalystOutput,
)

logger = logging.getLogger(__name__)


class IndustryAnalystAgent(Agent):
    """오케스트레이터에서 직접 호출하는 산업 분석 에이전트."""

    name = "industry_analyst"
    input_model = IndustryAnalystInput
    output_model = IndustryAnalystOutput

    def __init__(self, provider: IndustryDataProvider | None = None) -> None:
        self._provider = provider or ToolIndustryDataProvider()

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """업종 매핑, 산업 평균, 업황, 거시 신호를 분석한다."""
        started_at = perf_counter()
        request_id = payload.get("request_id")
        with request_id_context(request_id):
            company_name = payload.get("company_name")
            corp_code = str(payload.get("corp_code", "")).strip()
            if not corp_code:
                raise ValueError("industry_analyst 실행에는 corp_code가 필요합니다.")

            target_year = int(payload.get("target_year", 2024))
            tool_runs = []
            company_info, company_info_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="map_corp_to_ksic",
                request_id=request_id,
                company_name=company_name,
                runner=lambda: self._provider.map_corp_to_ksic(corp_code),
                fallback_factory=lambda: _default_company_info(company_name),
                validate_dict=True,
            )
            tool_runs.append(company_info_run)
            ksic_code = str(company_info.get("ksic_code", ""))
            company_ratios = payload.get("financial_ratios")

            industry_avg, industry_avg_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="get_industry_avg_ratios",
                request_id=request_id,
                company_name=company_name,
                runner=lambda: self._provider.get_industry_avg_ratios(
                    ksic_code,
                    target_year,
                    company_ratios,
                ),
                fallback_factory=lambda: _default_industry_summary(
                    ksic_code,
                    target_year,
                ),
                validate_dict=True,
            )
            tool_runs.append(industry_avg_run)
            industry_outlook, outlook_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="get_industry_outlook",
                request_id=request_id,
                company_name=company_name,
                runner=lambda: self._provider.get_industry_outlook(ksic_code),
                fallback_factory=lambda: _default_industry_outlook(ksic_code),
                validate_dict=True,
            )
            tool_runs.append(outlook_run)
            business_cycle, cycle_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="get_business_cycle",
                request_id=request_id,
                company_name=company_name,
                runner=self._provider.get_business_cycle,
                fallback_factory=_default_business_cycle,
                validate_dict=True,
            )
            tool_runs.append(cycle_run)
            macro_indicators, macro_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="get_macro_indicators",
                request_id=request_id,
                company_name=company_name,
                runner=lambda: self._provider.get_macro_indicators(ksic_code),
                fallback_factory=lambda: _default_macro_indicators(ksic_code),
                validate_dict=True,
            )
            tool_runs.append(macro_run)
            fallback_used, tool_errors = summarize_tool_runs(tool_runs)

            logger.info(
                (
                    "industry_analysis_finished company_name=%s corp_code=%s "
                    "ksic_code=%s tool_error_count=%s"
                ),
                company_name,
                corp_code,
                ksic_code,
                len(tool_errors),
            )

            return build_agent_output(
                {
                    "ksic_code": ksic_code,
                    "industry_summary": industry_avg,
                    "industry_outlook": industry_outlook,
                    "business_cycle": business_cycle,
                    "macro_indicators": macro_indicators,
                    "peer_comparison": industry_avg.get("peer_comparison"),
                    "industry_tool_runs": serialize_tool_runs(tool_runs),
                    "industry_tool_errors": tool_errors,
                },
                status="partial" if fallback_used else "success",
                error_code="INDUSTRY_TOOL_FALLBACK" if fallback_used else "OK",
                fallback_used=fallback_used,
                latency_ms=elapsed_ms(started_at),
            )


def _default_company_info(company_name: Any) -> dict[str, Any]:
    return {
        "corp_name": company_name or "",
        "ksic_code": "N/A",
    }


def _default_industry_summary(ksic_code: str, target_year: int) -> dict[str, Any]:
    return {
        "ksic_code": ksic_code,
        "year": target_year,
        "peer_comparison": None,
        "sector_note": "산업 평균 데이터를 불러오지 못했습니다.",
    }


def _default_industry_outlook(ksic_code: str) -> dict[str, Any]:
    return {
        "ksic_code": ksic_code,
        "outlook_score": "Medium",
        "note": "업황 데이터를 불러오지 못해 중립값을 적용했습니다.",
    }


def _default_business_cycle() -> dict[str, Any]:
    return {
        "phase": "unknown",
        "signal": "unavailable",
        "source": "fallback",
    }


def _default_macro_indicators(ksic_code: str) -> dict[str, Any]:
    return {
        "ksic_code": ksic_code,
        "note": "거시 지표를 불러오지 못했습니다.",
    }
