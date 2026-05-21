# ruff: noqa: E402

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from agents.base import Agent
from agents.orchestrator.orchestrator import WorkflowOrchestrator


class _FakeAgent(Agent):
    def __init__(
        self,
        name: str,
        output: dict[str, Any] | None = None,
        *,
        should_fail: bool = False,
    ) -> None:
        self.name = name
        self._output = output or {}
        self._should_fail = should_fail
        self.seen_contexts: list[dict[str, Any]] = []

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.seen_contexts.append(dict(payload))
        if self._should_fail:
            raise RuntimeError(f"{self.name} failed")
        return dict(self._output)


def test_orchestrator_stops_with_not_target_when_company_is_missing() -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": False,
            "workflow_status": "not_target",
            "workflow_code": "COMPANY_NOT_FOUND",
            "workflow_message": "대상 기업이 아닙니다.",
        },
    )
    parallel_agent = _FakeAgent("parallel_agent", {"parallel": True})
    sequential_agent = _FakeAgent("sequential_agent", {"sequential": True})

    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        parallel_agents=[parallel_agent],
        sequential_agents=[sequential_agent],
    )

    result = asyncio.run(orchestrator.run({"company_name": "없는기업"}))

    assert result["status"] == "not_target"
    assert result["code"] == "COMPANY_NOT_FOUND"
    assert len(result["steps"]) == 1
    assert parallel_agent.seen_contexts == []
    assert sequential_agent.seen_contexts == []


def test_orchestrator_passes_parallel_outputs_to_dependent_agents() -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": True,
            "corp_code": "00123456",
            "corp_name": "테스트기업",
        },
    )
    news_collector = _FakeAgent("news_collector", {"news_data": [{"title": "n1"}]})
    financial_analyst = _FakeAgent(
        "financial_analyst",
        {
            "financial_ratios": {"debt_ratio": 110.0},
            "grade_cap": "BB+",
        },
    )
    risk_event = _FakeAgent(
        "risk_event",
        {
            "critical_count": 0,
            "overall_risk_level": "low",
        },
    )
    industry_analyst = _FakeAgent(
        "industry_analyst",
        {
            "peer_comparison": {"debt_ratio_gap": -10.0},
        },
    )
    decision = _FakeAgent("decision", {"decision": "approve"})
    report = _FakeAgent("report", {"report": {"summary": "ok"}})

    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        parallel_agents=[
            news_collector,
            financial_analyst,
            risk_event,
            industry_analyst,
        ],
        sequential_agents=[decision, report],
    )

    result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "success"
    assert risk_event.seen_contexts[0]["news_data"] == [{"title": "n1"}]
    assert industry_analyst.seen_contexts[0]["financial_ratios"] == {
        "debt_ratio": 110.0
    }
    assert decision.seen_contexts[0]["grade_cap"] == "BB+"
    assert decision.seen_contexts[0]["peer_comparison"] == {
        "debt_ratio_gap": -10.0
    }
    assert decision.seen_contexts[0]["overall_risk_level"] == "low"
    assert result["context"]["report"] == {"summary": "ok"}
    assert {step["agent_name"] for step in result["steps"]} == {
        "company_resolver",
        "news_collector",
        "financial_analyst",
        "risk_event",
        "industry_analyst",
        "decision",
        "report",
    }


def test_orchestrator_halts_downstream_after_failure_by_default() -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": True,
            "corp_code": "00123456",
            "corp_name": "테스트기업",
        },
    )
    failing_news = _FakeAgent("news_collector", should_fail=True)
    risk_event = _FakeAgent("risk_event", {"overall_risk_level": "low"})
    decision = _FakeAgent("decision", {"decision": "approve"})

    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        parallel_agents=[failing_news, risk_event],
        sequential_agents=[decision],
    )

    result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "partial"
    assert any(
        step["agent_name"] == "news_collector" and step["ok"] is False
        for step in result["steps"]
    )
    assert risk_event.seen_contexts == []
    assert decision.seen_contexts == []


def test_orchestrator_returns_partial_when_failure_and_continue_on_error() -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": True,
            "corp_code": "00123456",
            "corp_name": "테스트기업",
        },
    )
    news_collector = _FakeAgent("news_collector", {"news_data": [{"title": "n1"}]})
    financial_analyst = _FakeAgent("financial_analyst", {"grade_cap": "BB+"})
    failing_industry = _FakeAgent("industry_analyst", should_fail=True)
    risk_event = _FakeAgent("risk_event", {"overall_risk_level": "medium"})
    decision = _FakeAgent("decision", {"decision": "review"})
    report = _FakeAgent("report", {"report": {"summary": "ok"}})

    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        parallel_agents=[
            news_collector,
            financial_analyst,
            risk_event,
            failing_industry,
        ],
        sequential_agents=[decision, report],
        continue_on_error=True,
    )

    result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "partial"
    assert decision.seen_contexts[0]["grade_cap"] == "BB+"
    assert decision.seen_contexts[0]["overall_risk_level"] == "medium"
    assert result["context"]["report"] == {"summary": "ok"}
    assert any(
        step["agent_name"] == "industry_analyst" and step["ok"] is False
        for step in result["steps"]
    )


def test_orchestrator_logs_agent_progress(caplog: Any) -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": True,
            "corp_code": "00123456",
            "corp_name": "테스트기업",
        },
    )
    news_collector = _FakeAgent("news_collector", {"news_data": [{"title": "n1"}]})
    decision = _FakeAgent("decision", {"decision": "approve"})

    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        parallel_agents=[news_collector],
        sequential_agents=[decision],
    )

    with caplog.at_level(logging.INFO, logger="agents.orchestrator.orchestrator"):
        result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "success"
    messages = [record.message for record in caplog.records]
    assert any("workflow_started company_name=테스트기업" in msg for msg in messages)
    assert any(
        "workflow_agent_started company_name=테스트기업 agent_name=company_resolver"
        in msg
        for msg in messages
    )
    assert any(
        "workflow_agent_completed company_name=테스트기업 agent_name=news_collector"
        in msg
        for msg in messages
    )
    assert any(
        "workflow_finished company_name=테스트기업 status=success" in msg
        for msg in messages
    )
