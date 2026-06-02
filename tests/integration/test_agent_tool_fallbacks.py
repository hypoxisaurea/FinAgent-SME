from __future__ import annotations

import asyncio
from typing import Any

from backend.agents.financial_analyst.agent import FinancialAnalystAgent
from backend.agents.industry_analyst.agent import IndustryAnalystAgent
from backend.agents.news_collector.agent import NewsCollectorAgent


class _FakeFinancialProvider:
    def get_financial_statements(self, corp_code: str, year: int) -> dict[str, Any]:
        raise RuntimeError("financial api down")

    def calc_financial_ratios(self, fs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def calc_altman_z_prime(self, fs: dict[str, Any]) -> dict[str, Any]:
        return {}

    def trend_analysis(self, corp_code: str, years: list[int]) -> dict[str, Any]:
        return {"history": [], "flags": [], "yoy": {}}

    def apply_risk_filters(
        self,
        fs: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "grade_cap": None,
            "triggered_filters": [],
            "filter_detail": {},
        }


class _FakeIndustryProvider:
    def map_corp_to_ksic(self, corp_code: str) -> dict[str, Any]:
        return {"corp_name": "테스트기업", "ksic_code": "C 제조업"}

    def get_industry_avg_ratios(
        self,
        ksic_code: str,
        year: int,
        company_ratios: Any,
    ) -> dict[str, Any]:
        return {"peer_comparison": {"gap": 1.2}}

    def get_industry_outlook(self, ksic_code: str) -> dict[str, Any]:
        return {"outlook_score": "High"}

    def get_business_cycle(self) -> dict[str, Any]:
        return {"phase": "확장"}

    def get_macro_indicators(self, ksic_code: str) -> dict[str, Any]:
        raise RuntimeError("macro api down")


class _FakeNewsProvider:
    def execute_news_pipeline(self, **_: Any) -> dict[str, Any]:
        raise RuntimeError("news pipeline failed")


def test_financial_agent_returns_partial_when_tool_fails() -> None:
    result = asyncio.run(
        FinancialAnalystAgent(provider=_FakeFinancialProvider()).run(
            {
                "company_name": "테스트기업",
                "corp_code": "00123456",
                "request_id": "req-test-fin",
            }
        )
    )

    assert result["status"] == "partial"
    assert result["fallback_used"] is True
    assert result["error_code"] == "FINANCIAL_TOOL_FALLBACK"
    assert result["financial_statements"] == {}
    assert any(
        error["tool_name"] == "get_financial_statements"
        for error in result["financial_tool_errors"]
    )
    assert any(
        tool_run["tool_name"] == "calc_financial_ratios"
        and tool_run["status"] == "skipped"
        for tool_run in result["financial_tool_runs"]
    )


def test_industry_agent_returns_partial_when_macro_tool_fails() -> None:
    result = asyncio.run(
        IndustryAnalystAgent(provider=_FakeIndustryProvider()).run(
            {
                "company_name": "테스트기업",
                "corp_code": "00123456",
                "request_id": "req-test-ind",
                "financial_ratios": {"debt_ratio": 120.0},
            }
        )
    )

    assert result["status"] == "partial"
    assert result["fallback_used"] is True
    assert result["error_code"] == "INDUSTRY_TOOL_FALLBACK"
    assert result["macro_indicators"]["note"] == "거시 지표를 불러오지 못했습니다."
    assert any(
        error["tool_name"] == "get_macro_indicators"
        for error in result["industry_tool_errors"]
    )


def test_news_collector_returns_partial_when_pipeline_raises() -> None:
    result = asyncio.run(
        NewsCollectorAgent(provider=_FakeNewsProvider()).run(
            {
                "company_name": "테스트기업",
                "request_id": "req-test-news",
            }
        )
    )

    assert result["status"] == "partial"
    assert result["fallback_used"] is True
    assert result["error_code"] == "NEWS_PIPELINE_DEGRADED"
    assert result["news_data"] == []
    assert any(
        error["tool_name"] == "execute_news_pipeline"
        for error in result["news_tool_errors"]
    )
