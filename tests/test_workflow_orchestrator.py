# ruff: noqa: E402

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from agents.base import Agent
from agents.orchestrator.orchestrator import WorkflowOrchestrator


class _FakeAgent(Agent):
    def __init__(self, name: str, output: dict | None = None, *, should_fail: bool = False) -> None:
        self.name = name
        self._output = output or {}
        self._should_fail = should_fail
        self.seen_contexts: list[dict] = []

    async def run(self, payload: dict) -> dict:
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


def test_orchestrator_runs_parallel_agents_before_sequential_agents() -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": True,
            "corp_code": "00123456",
            "corp_name": "테스트기업",
        },
    )
    parallel_a = _FakeAgent("news_collector", {"news_data": [{"title": "n1"}]})
    parallel_b = _FakeAgent("risk_event", {"critical_count": 0, "overall_risk_level": "low"})
    sequential = _FakeAgent("decision", {"decision": "approve"})

    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        parallel_agents=[parallel_a, parallel_b],
        sequential_agents=[sequential],
    )

    result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "success"
    assert result["context"]["corp_code"] == "00123456"
    assert result["context"]["decision"] == "approve"
    assert sequential.seen_contexts[0]["corp_code"] == "00123456"
    assert sequential.seen_contexts[0]["news_data"] == [{"title": "n1"}]
    assert [step["agent_name"] for step in result["steps"]] == [
        "company_resolver",
        "news_collector",
        "risk_event",
        "decision",
    ]


def test_orchestrator_returns_partial_when_parallel_agent_fails_with_continue_on_error() -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": True,
            "corp_code": "00123456",
            "corp_name": "테스트기업",
        },
    )
    failing_parallel = _FakeAgent("industry_analyst", should_fail=True)
    healthy_parallel = _FakeAgent("financial_analyst", {"grade_cap": "BB+"})
    sequential = _FakeAgent("report", {"report": {"summary": "ok"}})

    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        parallel_agents=[failing_parallel, healthy_parallel],
        sequential_agents=[sequential],
        continue_on_error=True,
    )

    result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "partial"
    assert result["context"]["grade_cap"] == "BB+"
    assert result["context"]["report"] == {"summary": "ok"}
    assert any(step["agent_name"] == "industry_analyst" and step["ok"] is False for step in result["steps"])
