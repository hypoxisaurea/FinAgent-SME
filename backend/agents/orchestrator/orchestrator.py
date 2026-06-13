from __future__ import annotations

import logging
from typing import Any

from backend.agents.company_resolver import CompanyResolverAgent
from backend.agents.decision import DecisionAgent
from backend.agents.financial_analyst import FinancialAnalystAgent
from backend.agents.industry_analyst import IndustryAnalystAgent
from backend.agents.multimodal_document import MultiModalDocumentAgent
from backend.agents.news_collector import NewsCollectorAgent
from backend.agents.orchestrator.graph import WorkflowGraphBuilder
from backend.agents.orchestrator.results import build_result, summarize_steps
from backend.agents.orchestrator.state import WorkflowState
from backend.agents.report import ReportAgent
from backend.agents.risk_event import RiskEventAgent
from backend.agents.validation import ValidationAgent
from backend.common.agent import Agent
from backend.common.langfuse import (
    propagate_trace_attributes,
    start_as_current_observation,
)
from backend.common.logging import request_id_context

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """의존성을 고려해 분석 에이전트를 병렬 실행하는 워크플로우 관리자."""

    def __init__(
        self,
        *,
        resolver_agent: Agent | None = None,
        parallel_agents: list[Agent] | None = None,
        sequential_agents: list[Agent] | None = None,
        continue_on_error: bool = False,
    ) -> None:
        self._resolver_agent = resolver_agent
        self._parallel_agents = parallel_agents or []
        self._sequential_agents = sequential_agents or []
        self._continue_on_error = continue_on_error
        self._validate_agents()
        self._graph = self._build_graph()

    def _validate_agents(self) -> None:
        candidates = [
            *([self._resolver_agent] if self._resolver_agent is not None else []),
            *self._parallel_agents,
            *self._sequential_agents,
        ]
        seen_names: set[str] = set()
        for agent in candidates:
            if not isinstance(agent, Agent):
                raise TypeError(
                    f"Agent 프로토콜 미준수 객체가 포함되어 있습니다: {agent!r}"
                )
            if agent.name in seen_names:
                raise ValueError(f"중복된 agent.name이 감지되었습니다: {agent.name}")
            seen_names.add(agent.name)

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        with request_id_context(payload.get("request_id")):
            with start_as_current_observation(
                name="credit_workflow",
                as_type="chain",
                input={"company_name": payload.get("company_name")},
                metadata={
                    "request_id": payload.get("request_id"),
                    "company_name": payload.get("company_name"),
                    "continue_on_error": self._continue_on_error,
                },
            ) as observation:
                with propagate_trace_attributes(
                    session_id=payload.get("request_id"),
                    tags=["credit_assessment", "orchestrator"],
                    metadata={
                        "feature": "credit_assessment",
                        "request_id": payload.get("request_id"),
                        "company_name": payload.get("company_name"),
                        "continue_on_error": self._continue_on_error,
                        "resolver_agent": getattr(self._resolver_agent, "name", None),
                        "parallel_agents": [
                            agent.name for agent in self._parallel_agents
                        ],
                        "sequential_agents": [
                            agent.name for agent in self._sequential_agents
                        ],
                    },
                ):
                    logger.info(
                        (
                            "workflow_started company_name=%s continue_on_error=%s "
                            "resolver_agent=%s parallel_agents=%s sequential_agents=%s"
                        ),
                        payload.get("company_name"),
                        self._continue_on_error,
                        getattr(self._resolver_agent, "name", None),
                        [agent.name for agent in self._parallel_agents],
                        [agent.name for agent in self._sequential_agents],
                    )
                    initial_state: WorkflowState = {
                        "context": dict(payload),
                        "steps": [],
                    }
                    final_state = await self._graph.ainvoke(initial_state)
                    result = build_result(final_state)
                    step_summary = summarize_steps(
                        [step.model_dump(mode="json") for step in result.steps]
                    )
                    observation.update(
                        output={
                            "status": result.status,
                            "step_count": len(result.steps),
                            "success_steps": step_summary["success"],
                            "partial_steps": step_summary["partial"],
                            "failed_steps": step_summary["failed"],
                            "fallback_steps": step_summary["fallback"],
                        }
                    )
                    logger.info(
                        (
                            "workflow_finished company_name=%s status=%s "
                            "step_count=%s success_steps=%s partial_steps=%s "
                            "failed_steps=%s fallback_steps=%s"
                        ),
                        payload.get("company_name"),
                        result.status,
                        len(result.steps),
                        step_summary["success"],
                        step_summary["partial"],
                        step_summary["failed"],
                        step_summary["fallback"],
                    )
                    return result.model_dump(mode="json", exclude_none=True)

    def _build_graph(self) -> Any:
        return WorkflowGraphBuilder(
            resolver_agent=self._resolver_agent,
            parallel_agents=self._parallel_agents,
            sequential_agents=self._sequential_agents,
            continue_on_error=self._continue_on_error,
        ).build()


def create_credit_workflow(
    resolver_agent: Agent | None = None,
    parallel_agents: list[Agent] | None = None,
    sequential_agents: list[Agent] | None = None,
    *,
    payload: dict[str, Any] | None = None,
    continue_on_error: bool = False,
) -> WorkflowOrchestrator:
    """신용심사 워크플로우 오케스트레이터 팩토리."""
    workflow_payload = payload or {}
    resolved_resolver = (
        resolver_agent if resolver_agent is not None else CompanyResolverAgent()
    )
    resolved_parallel = (
        parallel_agents
        if parallel_agents is not None
        else _build_parallel_agents(workflow_payload)
    )
    resolved_sequential = (
        sequential_agents
        if sequential_agents is not None
        else _build_sequential_agents()
    )
    return WorkflowOrchestrator(
        resolver_agent=resolved_resolver,
        parallel_agents=resolved_parallel,
        sequential_agents=resolved_sequential,
        continue_on_error=continue_on_error,
    )


async def run_credit_workflow(
    company_name: str,
    *,
    resolver_agent: Agent | None = None,
    parallel_agents: list[Agent] | None = None,
    sequential_agents: list[Agent] | None = None,
    extra_payload: dict[str, Any] | None = None,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    """멀티 에이전트 심사 파이프라인 진입점.

    기본 실행 순서:
      1. CompanyResolverAgent   — 대상 기업 여부 판별
      2. 1차 병렬 단계
         - NewsCollectorAgent
         - FinancialAnalystAgent
         - MultiModalDocumentAgent (pdf_path 있을 때만)
      3. 의존 단계
         - NewsCollectorAgent 이후 RiskEventAgent
         - FinancialAnalystAgent 이후 IndustryAnalystAgent
      4. 후속 심사 단계
         - DecisionAgent
         - ReportAgent
    """
    normalized_name = company_name.strip()
    if not normalized_name:
        raise ValueError("company_name은 비어 있을 수 없습니다.")

    payload: dict[str, Any] = {"company_name": normalized_name}
    if extra_payload:
        payload.update(extra_payload)
    payload.setdefault("collect_sources", ["news"])

    orchestrator = create_credit_workflow(
        resolver_agent=resolver_agent,
        parallel_agents=parallel_agents,
        sequential_agents=sequential_agents,
        payload=payload,
        continue_on_error=continue_on_error,
    )

    result = await orchestrator.run(payload)
    result["company_name"] = normalized_name
    return result


def _build_parallel_agents(payload: dict[str, Any]) -> list[Agent]:
    parallel_agents: list[Agent] = [
        NewsCollectorAgent(),
        FinancialAnalystAgent(),
        RiskEventAgent(),
        IndustryAnalystAgent(),
    ]
    if payload.get("pdf_path"):
        parallel_agents.append(MultiModalDocumentAgent())
    return parallel_agents


def _build_sequential_agents() -> list[Agent]:
    return [
        DecisionAgent(),
        ReportAgent(),
        ValidationAgent(),
    ]
