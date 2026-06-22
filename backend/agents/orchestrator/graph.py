from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from backend.agents.orchestrator.results import summarize_steps
from backend.agents.orchestrator.state import WorkflowState
from backend.agents.orchestrator.step_runner import run_agent_step
from backend.common.agent import Agent
from backend.common.langfuse import start_as_current_observation
from backend.common.langgraph import LANGGRAPH_IMPORT_GUARD
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger("backend.agents.orchestrator.orchestrator")
LANGGRAPH_RUNTIME_CONFIGURED = LANGGRAPH_IMPORT_GUARD
DEFAULT_VALIDATION_RETRY_ATTEMPTS = 1
MAX_VALIDATION_RETRY_ATTEMPTS = 3
VALIDATION_GATE_PASSED = "passed"
VALIDATION_GATE_RETRYING = "retrying"
VALIDATION_GATE_BLOCKED = "blocked"


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

            with start_as_current_observation(
                name=agent.name,
                as_type="agent",
                input={
                    "company_name": context.get("company_name"),
                    "agent_name": agent.name,
                },
                metadata={
                    "request_id": context.get("request_id"),
                    "company_name": context.get("company_name"),
                    "agent_name": agent.name,
                },
            ) as observation:
                logger.info(
                    "workflow_agent_started company_name=%s agent_name=%s",
                    context.get("company_name"),
                    agent.name,
                )
                step = await run_agent_step(agent, context)
                observation.update(
                    output={
                        "status": step.status,
                        "ok": step.ok,
                        "error_code": step.error_code,
                        "fallback_used": step.fallback_used,
                        "latency_ms": step.latency_ms,
                    }
                )
                node_state: WorkflowState = {"steps": [asdict(step)]}

                if agent.name == "validation":
                    validation_output = step.output
                    validation_result = validation_output.get("validation_result")
                    if not isinstance(validation_result, dict) or (
                        not step.ok
                        and validation_result.get("validation_passed") is True
                    ):
                        validation_output = self._build_validation_failure_output(step)
                    node_state["context"] = self._build_validation_gate_context(
                        context,
                        validation_output,
                    )
                    self._log_agent_result(context, agent, step)
                elif step.ok:
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

    def _build_validation_gate_context(
        self,
        context: dict[str, Any],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        validation_result = output["validation_result"]
        attempt = int(context.get("validation_attempt", 0)) + 1
        retry_attempts = (
            self._validation_retry_attempts(context)
            if self._validation_retry_node_name() is not None
            else 0
        )
        passed = validation_result.get("validation_passed") is True
        if passed:
            gate_status = VALIDATION_GATE_PASSED
        elif attempt <= retry_attempts:
            gate_status = VALIDATION_GATE_RETRYING
        else:
            gate_status = VALIDATION_GATE_BLOCKED
        logger.warning(
            (
                "workflow_validation_gate company_name=%s gate_status=%s "
                "attempt=%s retry_attempts=%s failed_checks=%s"
            ),
            context.get("company_name"),
            gate_status,
            attempt,
            retry_attempts,
            validation_result.get("failed_checks", []),
        )
        return {
            **output,
            "validation_attempt": attempt,
            "validation_retry_attempts": retry_attempts,
            "validation_gate_status": gate_status,
        }

    @staticmethod
    def _build_validation_failure_output(step: Any) -> dict[str, Any]:
        detail = step.error or step.error_code
        return {
            "validation_result": {
                "validation_passed": False,
                "pass_rate": 0.0,
                "passed_checks": 0,
                "total_checks": 1,
                "failed_checks": ["validation_execution"],
                "checks": [
                    {
                        "name": "validation_execution",
                        "passed": False,
                        "detail": detail,
                    }
                ],
            }
        }

    def _validation_retry_attempts(self, context: dict[str, Any]) -> int:
        value = context.get(
            "validation_retry_attempts",
            DEFAULT_VALIDATION_RETRY_ATTEMPTS,
        )
        if isinstance(value, bool) or not isinstance(value, int):
            return DEFAULT_VALIDATION_RETRY_ATTEMPTS
        return min(max(value, 0), MAX_VALIDATION_RETRY_ATTEMPTS)

    @staticmethod
    def _log_agent_result(context: dict[str, Any], agent: Agent, step: Any) -> None:
        log = logger.info if step.ok else logger.warning
        log(
            (
                "workflow_agent_completed company_name=%s agent_name=%s "
                "status=%s error_code=%s latency_ms=%s output_keys=%s"
            ),
            context.get("company_name"),
            agent.name,
            step.status,
            step.error_code,
            step.latency_ms,
            sorted(step.output.keys()),
        )

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

        last_agent = self._sequential_agents[-1]
        if last_agent.name == "validation":
            builder.add_conditional_edges(
                last_agent.name,
                self._route_after_validation,
            )
        else:
            builder.add_edge(last_agent.name, END)

    def _route_after_validation(self, state: WorkflowState) -> str:
        context = state.get("context", {})
        if context.get("validation_gate_status") != VALIDATION_GATE_RETRYING:
            return END
        retry_node = self._validation_retry_node_name()
        return retry_node or END

    def _validation_retry_node_name(self) -> str | None:
        if len(self._sequential_agents) < 2:
            return None
        retry_node = self._sequential_agents[-2].name
        return retry_node if retry_node == "report" else None

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
