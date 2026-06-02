from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from backend.common.agent import Agent
from backend.common.contracts import build_agent_output, elapsed_ms
from backend.common.logging import request_id_context
from backend.common.providers import (
    FinancialDataProvider,
    ToolFinancialDataProvider,
)
from backend.common.tool_runtime import (
    build_skipped_tool_result,
    execute_tool_step,
    serialize_tool_runs,
    summarize_tool_runs,
)

logger = logging.getLogger(__name__)


class FinancialAnalystAgent(Agent):
    """오케스트레이터에서 직접 호출하는 재무 분석 에이전트."""

    name = "financial_analyst"

    def __init__(self, provider: FinancialDataProvider | None = None) -> None:
        self._provider = provider or ToolFinancialDataProvider()

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """재무제표, 비율, 추세, 등급 상한을 계산한다."""
        started_at = perf_counter()
        request_id = payload.get("request_id")
        with request_id_context(request_id):
            company_name = payload.get("company_name")
            corp_code = str(payload.get("corp_code", "")).strip()
            if not corp_code:
                raise ValueError("financial_analyst 실행에는 corp_code가 필요합니다.")

            target_year = int(payload.get("target_year", 2024))
            years = _build_analysis_years(target_year)
            tool_runs = []

            fs, fs_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="get_financial_statements",
                request_id=request_id,
                company_name=company_name,
                runner=lambda: self._provider.get_financial_statements(
                    corp_code,
                    target_year,
                ),
                fallback_factory=lambda: {},
                validate_dict=True,
            )
            tool_runs.append(fs_run)

            if fs:
                ratios, ratios_run = execute_tool_step(
                    logger=logger,
                    agent_name=self.name,
                    tool_name="calc_financial_ratios",
                    request_id=request_id,
                    company_name=company_name,
                    runner=lambda: self._provider.calc_financial_ratios(fs),
                    fallback_factory=lambda: {},
                    validate_dict=True,
                )
                altman_z, altman_run = execute_tool_step(
                    logger=logger,
                    agent_name=self.name,
                    tool_name="calc_altman_z_prime",
                    request_id=request_id,
                    company_name=company_name,
                    runner=lambda: self._provider.calc_altman_z_prime(fs),
                    fallback_factory=lambda: _default_altman_z(),
                    validate_dict=True,
                )
            else:
                ratios = {}
                altman_z = _default_altman_z()
                ratios_run = build_skipped_tool_result(
                    tool_name="calc_financial_ratios",
                    reason="UPSTREAM_DATA_MISSING",
                )
                altman_run = build_skipped_tool_result(
                    tool_name="calc_altman_z_prime",
                    reason="UPSTREAM_DATA_MISSING",
                )
            tool_runs.extend([ratios_run, altman_run])

            trend, trend_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="trend_analysis",
                request_id=request_id,
                company_name=company_name,
                runner=lambda: self._provider.trend_analysis(corp_code, years),
                fallback_factory=lambda: _default_financial_trend(),
                validate_dict=True,
            )
            tool_runs.append(trend_run)

            risk_filters, risk_run = execute_tool_step(
                logger=logger,
                agent_name=self.name,
                tool_name="apply_risk_filters",
                request_id=request_id,
                company_name=company_name,
                runner=lambda: self._provider.apply_risk_filters(
                    fs,
                    trend.get("history", []),
                ),
                fallback_factory=lambda: _default_risk_filters(),
                validate_dict=True,
            )
            tool_runs.append(risk_run)
            fallback_used, tool_errors = summarize_tool_runs(tool_runs)

            logger.info(
                (
                    "financial_analysis_finished company_name=%s corp_code=%s "
                    "target_year=%s grade_cap=%s tool_error_count=%s"
                ),
                company_name,
                corp_code,
                target_year,
                risk_filters.get("grade_cap"),
                len(tool_errors),
            )

            return build_agent_output(
                {
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
                        "tool_error_count": len(tool_errors),
                    },
                    "financial_tool_runs": serialize_tool_runs(tool_runs),
                    "financial_tool_errors": tool_errors,
                },
                status="partial" if fallback_used else "success",
                error_code="FINANCIAL_TOOL_FALLBACK" if fallback_used else "OK",
                fallback_used=fallback_used,
                latency_ms=elapsed_ms(started_at),
            )


def _build_analysis_years(target_year: int) -> list[int]:
    start_year = max(target_year - 2, 1)
    return list(range(start_year, target_year + 1))


def _default_altman_z() -> dict[str, Any]:
    return {
        "z_prime": None,
        "zone": "unavailable",
        "components": {},
    }


def _default_financial_trend() -> dict[str, Any]:
    return {
        "history": [],
        "flags": [],
        "yoy": {},
    }


def _default_risk_filters() -> dict[str, Any]:
    return {
        "grade_cap": None,
        "triggered_filters": [],
        "filter_detail": {},
    }
