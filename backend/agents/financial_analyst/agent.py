from __future__ import annotations

import logging
from typing import Any

from agents.base import Agent
from agents.financial_analyst.financial_tools import (
    apply_risk_filters,
    calc_altman_z_prime,
    calc_financial_ratios,
    get_financial_statements,
    trend_analysis,
)

logger = logging.getLogger(__name__)


class FinancialAnalystAgent(Agent):
    """오케스트레이터에서 직접 호출하는 재무 분석 에이전트."""

    name = "financial_analyst"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """재무제표, 비율, 추세, 등급 상한을 계산한다."""
        corp_code = str(payload.get("corp_code", "")).strip()
        if not corp_code:
            raise ValueError("financial_analyst 실행에는 corp_code가 필요합니다.")

        target_year = int(payload.get("target_year", 2024))
        years = _build_analysis_years(target_year)

        fs = get_financial_statements.invoke(
            {"corp_code": corp_code, "year": target_year}
        )
        ratios = calc_financial_ratios.invoke({"fs": fs})
        altman_z = calc_altman_z_prime.invoke({"fs": fs})
        trend = trend_analysis.invoke({"corp_code": corp_code, "years": years})
        risk_filters = apply_risk_filters.invoke(
            {"fs": fs, "history": trend.get("history", [])}
        )

        logger.info(
            "financial_analysis_finished corp_code=%s target_year=%s grade_cap=%s",
            corp_code,
            target_year,
            risk_filters.get("grade_cap"),
        )

        return {
            "financial_statements": fs,
            "financial_ratios": ratios,
            "company_ratios": ratios,
            "altman_z": altman_z,
            "financial_trend": trend,
            "financial_flags": trend.get("flags", []),
            "risk_filters": risk_filters,
            "grade_cap": risk_filters.get("grade_cap"),
            "total_assets": fs.get("총자산"),
            "total_assets_statement": fs.get("총자산"),
            "revenue": fs.get("매출액"),
            "operating_income": fs.get("영업이익"),
            "net_income": fs.get("당기순이익"),
            "financial_summary": {
                "target_year": target_year,
                "years_analyzed": years,
                "grade_cap": risk_filters.get("grade_cap"),
                "triggered_filters": risk_filters.get("triggered_filters", []),
                "z_prime": altman_z.get("z_prime"),
                "z_prime_zone": altman_z.get("zone"),
            },
        }


def _build_analysis_years(target_year: int) -> list[int]:
    start_year = max(target_year - 2, 1)
    return list(range(start_year, target_year + 1))
