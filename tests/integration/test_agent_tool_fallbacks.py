from __future__ import annotations

import asyncio

import agents.financial_analyst.agent as financial_agent_module
import agents.industry_analyst.agent as industry_agent_module
import agents.news_collector.agent as news_agent_module
from agents.financial_analyst.agent import FinancialAnalystAgent
from agents.industry_analyst.agent import IndustryAnalystAgent
from agents.news_collector.agent import NewsCollectorAgent


class _DummyTool:
    def __init__(self, invoke):
        self.invoke = invoke


def test_financial_agent_returns_partial_when_tool_fails(
    monkeypatch,
) -> None:
    def _raise_financials(_: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("financial api down")

    monkeypatch.setattr(
        financial_agent_module,
        "get_financial_statements",
        _DummyTool(_raise_financials),
    )
    monkeypatch.setattr(
        financial_agent_module,
        "trend_analysis",
        _DummyTool(lambda _: {"history": [], "flags": [], "yoy": {}}),
    )
    monkeypatch.setattr(
        financial_agent_module,
        "apply_risk_filters",
        _DummyTool(
            lambda _: {
                "grade_cap": None,
                "triggered_filters": [],
                "filter_detail": {},
            }
        ),
    )

    result = asyncio.run(
        FinancialAnalystAgent().run(
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


def test_industry_agent_returns_partial_when_macro_tool_fails(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        industry_agent_module,
        "map_corp_to_ksic",
        _DummyTool(lambda _: {"corp_name": "테스트기업", "ksic_code": "C 제조업"}),
    )
    monkeypatch.setattr(
        industry_agent_module,
        "get_industry_avg_ratios",
        _DummyTool(lambda _: {"peer_comparison": {"gap": 1.2}}),
    )
    monkeypatch.setattr(
        industry_agent_module,
        "get_industry_outlook",
        _DummyTool(lambda _: {"outlook_score": "High"}),
    )
    monkeypatch.setattr(
        industry_agent_module,
        "get_business_cycle",
        _DummyTool(lambda _: {"phase": "확장"}),
    )

    def _raise_macro(_: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("macro api down")

    monkeypatch.setattr(
        industry_agent_module,
        "get_macro_indicators",
        _DummyTool(_raise_macro),
    )

    result = asyncio.run(
        IndustryAnalystAgent().run(
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


def test_news_collector_returns_partial_when_pipeline_raises(
    monkeypatch,
) -> None:
    def _raise_pipeline(**_: object) -> dict[str, object]:
        raise RuntimeError("news pipeline failed")

    monkeypatch.setattr(news_agent_module, "execute_news_pipeline", _raise_pipeline)

    result = asyncio.run(
        NewsCollectorAgent().run(
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
