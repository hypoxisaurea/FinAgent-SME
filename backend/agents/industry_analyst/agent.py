from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from agents.base import Agent
from agents.contracts import build_agent_output, elapsed_ms
from agents.industry_analyst.industry_tools import (
    get_business_cycle,
    get_industry_avg_ratios,
    get_industry_outlook,
    get_macro_indicators,
    map_corp_to_ksic,
)

logger = logging.getLogger(__name__)


class IndustryAnalystAgent(Agent):
    """오케스트레이터에서 직접 호출하는 산업 분석 에이전트."""

    name = "industry_analyst"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """업종 매핑, 산업 평균, 업황, 거시 신호를 분석한다."""
        started_at = perf_counter()
        corp_code = str(payload.get("corp_code", "")).strip()
        if not corp_code:
            raise ValueError("industry_analyst 실행에는 corp_code가 필요합니다.")

        target_year = int(payload.get("target_year", 2024))
        company_info = map_corp_to_ksic.invoke({"corp_code": corp_code})
        ksic_code = str(company_info.get("ksic_code", ""))
        company_ratios = payload.get("financial_ratios")

        industry_avg = get_industry_avg_ratios.invoke(
            {
                "ksic_code": ksic_code,
                "year": target_year,
                "company_ratios": company_ratios,
            }
        )
        industry_outlook = get_industry_outlook.invoke({"ksic_code": ksic_code})
        business_cycle = get_business_cycle.invoke({})
        macro_indicators = get_macro_indicators.invoke({"ksic_code": ksic_code})

        logger.info(
            "industry_analysis_finished corp_code=%s ksic_code=%s",
            corp_code,
            ksic_code,
        )

        return build_agent_output(
            {
                "ksic_code": ksic_code,
                "industry_summary": industry_avg,
                "industry_outlook": industry_outlook,
                "business_cycle": business_cycle,
                "macro_indicators": macro_indicators,
                "peer_comparison": industry_avg.get("peer_comparison"),
            },
            latency_ms=elapsed_ms(started_at),
        )
