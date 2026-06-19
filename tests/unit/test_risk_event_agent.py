from __future__ import annotations

import asyncio
from datetime import date

from backend.agents.risk_event.agent import RiskEventAgent
from backend.agents.risk_event.models import (
    EventSource,
    EventType,
    RiskEvent,
    RiskEventResult,
    SeverityClassifiedEvent,
    SeverityLevel,
)
from backend.agents.orchestrator.step_runner import run_agent_step


def test_risk_event_agent_accepts_request_id(monkeypatch) -> None:
    async def fake_run_risk_event_agent(**kwargs) -> RiskEventResult:
        assert kwargs["request_id"] == "req-123"
        return RiskEventResult(
            company_name=kwargs["company_name"],
            corp_code=kwargs["corp_code"],
            overall_risk_level=SeverityLevel.LOW,
            processed_at=date.today(),
        )

    monkeypatch.setattr(
        "backend.agents.risk_event.agent.run_risk_event_agent",
        fake_run_risk_event_agent,
    )

    async def _run() -> dict[str, object]:
        agent = RiskEventAgent()
        return await agent.run(
            {
                "request_id": "req-123",
                "company_name": "케이씨피드",
                "corp_code": "00123456",
                "news_data": [],
                "disclosure_data": [],
                "court_data": [],
            }
        )

    result = asyncio.run(_run())

    assert result["status"] == "success"
    assert result["error_code"] == "OK"
    assert result["company_name"] == "케이씨피드"
    assert result["corp_code"] == "00123456"


def test_risk_event_agent_nested_output_satisfies_runner_contract(monkeypatch) -> None:
    event = RiskEvent(
        event_type=EventType.NEGATIVE_KEYWORD,
        source=EventSource.NEWS,
        title="부정 뉴스",
        description="유동성 위험이 언급됨",
        detected_at=date.today(),
    )
    classified_event = SeverityClassifiedEvent(
        event=event,
        severity=SeverityLevel.HIGH,
        score=80,
        rationale="신용 위험 가능성",
    )

    async def fake_run_risk_event_agent(**kwargs) -> RiskEventResult:
        return RiskEventResult(
            company_name=kwargs["company_name"],
            corp_code=kwargs["corp_code"],
            all_events=[event],
            classified_events=[classified_event],
            high_count=1,
            total_event_count=1,
            overall_risk_level=SeverityLevel.HIGH,
        )

    monkeypatch.setattr(
        "backend.agents.risk_event.agent.run_risk_event_agent",
        fake_run_risk_event_agent,
    )

    step = asyncio.run(
        run_agent_step(
            RiskEventAgent(),
            {
                "request_id": "req-nested-output",
                "company_name": "러셀",
                "corp_code": "01068348",
                "news_data": [{"title": "부정 뉴스"}],
            },
        )
    )

    assert step.ok is True
    assert step.error_code == "OK"
    assert step.output["overall_risk_level"] == SeverityLevel.HIGH
    assert step.output["classified_events"][0]["score"] == 80
