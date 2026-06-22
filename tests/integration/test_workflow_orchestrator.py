from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.agents.orchestrator.orchestrator import WorkflowOrchestrator
from backend.agents.orchestrator.orchestrator import create_credit_workflow
from backend.common.agent import Agent


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


class _SequenceAgent(_FakeAgent):
    def __init__(self, name: str, outputs: list[dict[str, Any]]) -> None:
        super().__init__(name)
        self._outputs = outputs

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.seen_contexts.append(dict(payload))
        return dict(self._outputs[len(self.seen_contexts) - 1])


def _assert_common_step_contract(steps: list[dict[str, Any]]) -> None:
    for step in steps:
        assert "status" in step
        assert "error_code" in step
        assert "fallback_used" in step
        assert "latency_ms" in step
        assert isinstance(step["fallback_used"], bool)
        assert isinstance(step["latency_ms"], int)


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
    _assert_common_step_contract(result["steps"])
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
    _assert_common_step_contract(result["steps"])
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
    assert "status" not in result["context"]
    assert "error_code" not in result["context"]
    assert "fallback_used" not in result["context"]
    assert "latency_ms" not in result["context"]
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
    _assert_common_step_contract(result["steps"])
    assert any(
        step["agent_name"] == "news_collector" and step["ok"] is False
        for step in result["steps"]
    )
    assert "_halt_workflow" not in result["context"]
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
    _assert_common_step_contract(result["steps"])
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

    with caplog.at_level(logging.INFO, logger="backend.agents.orchestrator.orchestrator"):
        result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "success"
    _assert_common_step_contract(result["steps"])
    messages = [record.message for record in caplog.records]
    request_ids = [record.request_id for record in caplog.records]
    assert any(request_id == "-" for request_id in request_ids)
    assert any(
        "workflow_started company_name=테스트기업" in msg
        for msg in messages
    )
    assert any(
        (
            "workflow_agent_started company_name=테스트기업 agent_name=company_resolver"
        )
        in msg
        for msg in messages
    )
    assert any(
        (
            "workflow_agent_completed company_name=테스트기업 "
            "agent_name=news_collector"
        )
        in msg
        for msg in messages
    )
    assert any(
        (
            "workflow_progress company_name=테스트기업 completed_steps=3"
        )
        in msg
        for msg in messages
    )
    assert any(
        (
            "workflow_finished company_name=테스트기업 status=success"
        )
        in msg
        for msg in messages
    )


def test_default_credit_workflow_includes_validation_agent() -> None:
    orchestrator = create_credit_workflow(payload={"company_name": "테스트기업"})

    assert [agent.name for agent in orchestrator._sequential_agents] == [
        "decision",
        "report",
        "validation",
    ]


def test_orchestrator_retries_report_then_blocks_failed_validation(caplog: Any) -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": True,
            "corp_code": "00123456",
            "corp_name": "테스트기업",
        },
    )
    decision = _FakeAgent(
        "decision",
        {"decision": "reject", "recommended_limit": 0},
    )
    report = _FakeAgent("report", {"report": {"summary": "검증 전 보고서"}})
    validation = _FakeAgent(
        "validation",
        {
            "status": "failed",
            "error_code": "VALIDATION_FAILED",
            "validation_result": {
                "validation_passed": False,
                "pass_rate": 0.8,
                "passed_checks": 4,
                "total_checks": 5,
                "failed_checks": ["reject_limit_rule"],
                "checks": [],
            },
        },
    )
    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        sequential_agents=[decision, report, validation],
    )

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "failed"
    assert result["code"] == "VALIDATION_FAILED"
    assert result["message"] == "최종 결과 검증에 실패하여 심사 결과가 차단되었습니다."
    assert "report" not in result["context"]
    assert result["context"]["validation_result"]["validation_passed"] is False
    assert result["context"]["validation_gate_status"] == "blocked"
    assert result["context"]["validation_attempt"] == 2
    assert len(report.seen_contexts) == 2
    decision_step = next(
        step for step in result["steps"] if step["agent_name"] == "decision"
    )
    assert "decision" not in decision_step["output"]
    assert "recommended_limit" not in decision_step["output"]
    report_steps = [step for step in result["steps"] if step["agent_name"] == "report"]
    assert all("report" not in step["output"] for step in report_steps)
    validation_steps = [
        step for step in result["steps"] if step["agent_name"] == "validation"
    ]
    assert len(validation_steps) == 2
    assert all(step["ok"] is False for step in validation_steps)
    assert all(step["status"] == "failed" for step in validation_steps)
    assert all(step["error_code"] == "VALIDATION_FAILED" for step in validation_steps)
    assert any(
        "workflow_validation_blocked" in record.message for record in caplog.records
    )


def test_orchestrator_releases_result_when_validation_retry_passes() -> None:
    report = _SequenceAgent(
        "report",
        [
            {"report": {"summary": "첫 보고서"}},
            {"report": {"summary": "수정 보고서"}},
        ],
    )
    validation = _SequenceAgent(
        "validation",
        [
            {
                "status": "failed",
                "error_code": "VALIDATION_FAILED",
                "validation_result": {
                    "validation_passed": False,
                    "pass_rate": 0.5,
                    "passed_checks": 1,
                    "total_checks": 2,
                    "failed_checks": ["report_summary_present"],
                    "checks": [],
                },
            },
            {
                "validation_result": {
                    "validation_passed": True,
                    "pass_rate": 1.0,
                    "passed_checks": 2,
                    "total_checks": 2,
                    "failed_checks": [],
                    "checks": [],
                },
            },
        ],
    )
    orchestrator = WorkflowOrchestrator(
        sequential_agents=[report, validation],
    )

    result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "success"
    assert result.get("code") is None
    assert result["context"]["report"] == {"summary": "수정 보고서"}
    assert result["context"]["validation_gate_status"] == "passed"
    assert result["context"]["validation_attempt"] == 2


def test_orchestrator_can_block_validation_without_retry() -> None:
    report = _FakeAgent("report", {"report": {"summary": "차단 보고서"}})
    validation = _FakeAgent(
        "validation",
        {
            "status": "failed",
            "error_code": "VALIDATION_FAILED",
            "validation_result": {
                "validation_passed": False,
                "pass_rate": 0.0,
                "passed_checks": 0,
                "total_checks": 1,
                "failed_checks": ["report_present"],
                "checks": [],
            },
        },
    )
    orchestrator = WorkflowOrchestrator(sequential_agents=[report, validation])

    result = asyncio.run(
        orchestrator.run(
            {"company_name": "테스트기업", "validation_retry_attempts": 0}
        )
    )

    assert result["status"] == "failed"
    assert result["context"]["validation_attempt"] == 1
    assert len(report.seen_contexts) == 1


def test_orchestrator_blocks_when_validation_has_no_report_retry_node() -> None:
    validation = _FakeAgent(
        "validation",
        {
            "status": "failed",
            "error_code": "VALIDATION_FAILED",
            "validation_result": {
                "validation_passed": False,
                "pass_rate": 0.0,
                "passed_checks": 0,
                "total_checks": 1,
                "failed_checks": ["report_present"],
                "checks": [],
            },
        },
    )
    orchestrator = WorkflowOrchestrator(sequential_agents=[validation])

    result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "failed"
    assert result["context"]["validation_gate_status"] == "blocked"
    assert result["context"]["validation_retry_attempts"] == 0


def test_orchestrator_blocks_and_redacts_when_validation_execution_fails() -> None:
    report = _FakeAgent("report", {"report": {"summary": "차단 보고서"}})
    validation = _FakeAgent(
        "validation",
        {
            "status": "failed",
            "error_code": "AGENT_EXECUTION_FAILED",
        },
    )
    orchestrator = WorkflowOrchestrator(
        sequential_agents=[report, validation],
    )

    result = asyncio.run(
        orchestrator.run({"company_name": "테스트기업", "validation_retry_attempts": 0})
    )

    assert result["status"] == "failed"
    assert result["code"] == "VALIDATION_FAILED"
    assert result["context"]["validation_gate_status"] == "blocked"
    assert result["context"]["validation_result"]["failed_checks"] == [
        "validation_execution"
    ]
    assert "report" not in result["context"]
    report_step = next(
        step for step in result["steps"] if step["agent_name"] == "report"
    )
    assert "report" not in report_step["output"]


def test_orchestrator_fails_closed_for_inconsistent_validation_status() -> None:
    report = _FakeAgent("report", {"report": {"summary": "차단 보고서"}})
    validation = _FakeAgent(
        "validation",
        {
            "status": "failed",
            "error_code": "AGENT_EXECUTION_FAILED",
            "validation_result": {
                "validation_passed": True,
                "pass_rate": 1.0,
                "passed_checks": 1,
                "total_checks": 1,
                "failed_checks": [],
                "checks": [],
            },
        },
    )
    orchestrator = WorkflowOrchestrator(
        sequential_agents=[report, validation],
    )

    result = asyncio.run(
        orchestrator.run({"company_name": "테스트기업", "validation_retry_attempts": 0})
    )

    assert result["status"] == "failed"
    assert result["code"] == "VALIDATION_FAILED"
    assert result["context"]["validation_gate_status"] == "blocked"
    assert result["context"]["validation_result"]["validation_passed"] is False
    assert result["context"]["validation_result"]["failed_checks"] == [
        "validation_execution"
    ]


def test_orchestrator_marks_failed_contract_output_as_step_failure() -> None:
    resolver = _FakeAgent(
        "company_resolver",
        {
            "company_found": True,
            "corp_code": "00123456",
            "corp_name": "테스트기업",
        },
    )
    decision = _FakeAgent(
        "decision",
        {
            "status": "failed",
            "error_code": "DECISION_OUTPUT_MISSING",
            "fallback_used": False,
            "decision_output": None,
        },
    )

    orchestrator = WorkflowOrchestrator(
        resolver_agent=resolver,
        sequential_agents=[decision],
    )

    result = asyncio.run(orchestrator.run({"company_name": "테스트기업"}))

    assert result["status"] == "partial"
    _assert_common_step_contract(result["steps"])
    decision_step = next(
        step for step in result["steps"] if step["agent_name"] == "decision"
    )
    assert decision_step["ok"] is False
    assert decision_step["status"] == "failed"
    assert decision_step["error_code"] == "DECISION_OUTPUT_MISSING"
