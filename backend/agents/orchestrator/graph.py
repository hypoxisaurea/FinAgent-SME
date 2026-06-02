from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from backend.agents.orchestrator.results import summarize_steps
from backend.agents.orchestrator.state import WorkflowState
from backend.agents.orchestrator.step_runner import run_agent_step
from backend.common.agent import Agent
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger("backend.agents.orchestrator.orchestrator")


class WorkflowGraphBuilder:
    """오케스트레이터 그래프 구성과 라우팅 규칙을 담당한다."""

    def __init__(
        self,
        *,
        resolver_agent: Agent | None,
        parallel_agents: list[Agent],
        sequential_agents: list[Agent],
        continue_on_error: bool,
    ) -> None:
        self._resolver_agent = resolver_agent
        self._parallel_agents = parallel_agents
        self._sequential_agents = sequential_agents
        self._continue_on_error = continue_on_error
        self._news_agent = self._find_parallel_agent("news_collector")
        self._financial_agent = self._find_parallel_agent("financial_analyst")

    def build(self) -> Any:
        builder = StateGraph(WorkflowState)
        all_agents = self._all_graph_agents()

        for agent in all_agents:
            builder.add_node(
                agent.name,
                self._create_agent_node(agent),
            )

        if self._resolver_agent is not None:
            builder.add_edge(START, self._resolver_agent.name)
            builder.add_conditional_edges(
                self._resolver_agent.name,
                self._route_after_resolver,
            )
        else:
            builder.add_conditional_edges(START, self._route_from_start)

        self._connect_analysis_agents(builder)
        self._connect_sequential_agents(builder)
        return builder.compile()

    def _all_graph_agents(self) -> list[Agent]:
        ordered_agents: list[Agent] = []
        if self._resolver_agent is not None:
            ordered_agents.append(self._resolver_agent)
        ordered_agents.extend(self._parallel_agents)
        ordered_agents.extend(self._sequential_agents)
        return ordered_agents

    def _create_agent_node(self, agent: Agent) -> Any:
        async def _node(state: WorkflowState) -> WorkflowState:
            context = dict(state.get("context", {}))
            if context.get("_halt_workflow"):
                return {}

            logger.info(
                "workflow_agent_started company_name=%s agent_name=%s",
                context.get("company_name"),
                agent.name,
            )
            step = await run_agent_step(agent, context)
            node_state: WorkflowState = {"steps": [asdict(step)]}

            if step.ok:
                logger.info(
                    (
                        "workflow_agent_completed company_name=%s agent_name=%s "
                        "status=%s fallback_used=%s "
                        "latency_ms=%s output_keys=%s"
                    ),
                    context.get("company_name"),
                    agent.name,
                    step.status,
                    step.fallback_used,
                    step.latency_ms,
                    sorted(step.output.keys()),
                )
                if step.output:
                    node_state["context"] = step.output
            elif not self._continue_on_error:
                logger.warning(
                    (
                        "workflow_agent_failed company_name=%s agent_name=%s "
                        "status=%s error_code=%s "
                        "continue_on_error=%s error=%s"
                    ),
                    context.get("company_name"),
                    agent.name,
                    step.status,
                    step.error_code,
                    self._continue_on_error,
                    step.error,
                )
                node_state["context"] = {"_halt_workflow": True}
            else:
                logger.warning(
                    (
                        "workflow_agent_failed company_name=%s agent_name=%s "
                        "status=%s error_code=%s "
                        "continue_on_error=%s error=%s"
                    ),
                    context.get("company_name"),
                    agent.name,
                    step.status,
                    step.error_code,
                    self._continue_on_error,
                    step.error,
                )

            progress_steps = list(state.get("steps", [])) + [asdict(step)]
            progress_summary = summarize_steps(progress_steps)
            logger.info(
                (
                    "workflow_progress company_name=%s completed_steps=%s "
                    "success_steps=%s partial_steps=%s "
                    "failed_steps=%s fallback_steps=%s last_agent=%s last_status=%s"
                ),
                context.get("company_name"),
                len(progress_steps),
                progress_summary["success"],
                progress_summary["partial"],
                progress_summary["failed"],
                progress_summary["fallback"],
                agent.name,
                step.status,
            )

            return node_state

        return _node

    def _route_after_resolver(self, state: WorkflowState) -> str | list[str]:
        context = state.get("context", {})
        if context.get("company_found") is False or context.get("_halt_workflow"):
            return END
        return self._route_to_start_nodes()

    def _route_from_start(self, state: WorkflowState) -> str | list[str]:
        context = state.get("context", {})
        if context.get("_halt_workflow"):
            return END
        return self._route_to_start_nodes()

    def _route_to_start_nodes(self) -> str | list[str]:
        start_nodes = self._analysis_start_node_names()
        if start_nodes:
            return start_nodes
        first_sequential = self._first_sequential_agent_name()
        return first_sequential or END

    def _analysis_start_node_names(self) -> list[str]:
        node_names: list[str] = []
        for agent in self._parallel_agents:
            if agent.name == "risk_event" and self._news_agent is not None:
                continue
            if agent.name == "industry_analyst" and self._financial_agent is not None:
                continue
            node_names.append(agent.name)
        return node_names

    def _analysis_terminal_node_names(self) -> list[str]:
        node_names: list[str] = []
        for agent in self._parallel_agents:
            if agent.name == "news_collector" and self._has_parallel_agent("risk_event"):
                continue
            if agent.name == "financial_analyst" and self._has_parallel_agent(
                "industry_analyst"
            ):
                continue
            node_names.append(agent.name)
        return node_names

    def _connect_analysis_agents(self, builder: StateGraph) -> None:
        if self._has_parallel_agent("risk_event") and self._news_agent is not None:
            builder.add_edge(self._news_agent.name, "risk_event")

        if (
            self._has_parallel_agent("industry_analyst")
            and self._financial_agent is not None
        ):
            builder.add_edge(self._financial_agent.name, "industry_analyst")

    def _connect_sequential_agents(self, builder: StateGraph) -> None:
        if not self._sequential_agents:
            for terminal_name in self._analysis_terminal_node_names():
                builder.add_edge(terminal_name, END)
            return

        first_sequential = self._sequential_agents[0].name
        for terminal_name in self._analysis_terminal_node_names():
            builder.add_edge(terminal_name, first_sequential)

        for current_agent, next_agent in zip(
            self._sequential_agents,
            self._sequential_agents[1:],
        ):
            builder.add_edge(current_agent.name, next_agent.name)

        builder.add_edge(self._sequential_agents[-1].name, END)

    def _find_parallel_agent(self, name: str) -> Agent | None:
        for agent in self._parallel_agents:
            if agent.name == name:
                return agent
        return None

    def _has_parallel_agent(self, name: str) -> bool:
        return self._find_parallel_agent(name) is not None

    def _first_sequential_agent_name(self) -> str | None:
        if not self._sequential_agents:
            return None
        return self._sequential_agents[0].name
