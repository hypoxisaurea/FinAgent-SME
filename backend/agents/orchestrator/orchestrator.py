from __future__ import annotations

import asyncio
import logging
import operator
from dataclasses import asdict, dataclass
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import Agent
from agents.company_resolver import CompanyResolverAgent
from agents.contracts import (
    build_agent_failure_output,
    build_agent_output,
    classify_agent_error,
    extract_agent_business_output,
    extract_agent_execution,
    is_agent_step_ok,
    resolve_agent_retry_attempts,
    resolve_agent_retry_backoff_seconds,
    resolve_agent_timeout_seconds,
    should_retry_agent_error,
)
from agents.decision import DecisionAgent
from agents.financial_analyst import FinancialAnalystAgent
from agents.industry_analyst import IndustryAnalystAgent
from agents.multimodal_document import MultiModalDocumentAgent
from agents.news_collector import NewsCollectorAgent
from agents.report import ReportAgent
from agents.risk_event import RiskEventAgent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StepResult:
    """오케스트레이션 단일 단계 실행 결과."""

    agent_name: str
    ok: bool
    status: str
    error_code: str
    fallback_used: bool
    latency_ms: int
    output: dict[str, Any]
    error: str | None = None


def _merge_context(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(left or {})
    merged.update(right or {})
    return merged


class WorkflowState(TypedDict, total=False):
    """LangGraph 오케스트레이션 상태."""

    context: Annotated[dict[str, Any], _merge_context]
    steps: Annotated[list[dict[str, Any]], operator.add]


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
        self._news_agent = self._find_parallel_agent("news_collector")
        self._financial_agent = self._find_parallel_agent("financial_analyst")
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
        request_id = payload.get("request_id")
        logger.info(
            (
                "workflow_started request_id=%s company_name=%s continue_on_error=%s "
                "resolver_agent=%s parallel_agents=%s sequential_agents=%s"
            ),
            request_id,
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
        result = _build_result(final_state)
        step_summary = _summarize_steps(result["steps"])
        logger.info(
            (
                "workflow_finished request_id=%s company_name=%s status=%s "
                "step_count=%s success_steps=%s partial_steps=%s "
                "failed_steps=%s fallback_steps=%s"
            ),
            request_id,
            payload.get("company_name"),
            result["status"],
            len(result["steps"]),
            step_summary["success"],
            step_summary["partial"],
            step_summary["failed"],
            step_summary["fallback"],
        )
        return result

    def _build_graph(self) -> Any:
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
                "workflow_agent_started request_id=%s company_name=%s agent_name=%s",
                context.get("request_id"),
                context.get("company_name"),
                agent.name,
            )
            step = await _run_agent_step(agent, context)
            node_state: WorkflowState = {"steps": [asdict(step)]}

            if step.ok:
                logger.info(
                    (
                        "workflow_agent_completed request_id=%s company_name=%s "
                        "agent_name=%s status=%s fallback_used=%s "
                        "latency_ms=%s output_keys=%s"
                    ),
                    context.get("request_id"),
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
                        "workflow_agent_failed request_id=%s company_name=%s "
                        "agent_name=%s status=%s error_code=%s "
                        "continue_on_error=%s error=%s"
                    ),
                    context.get("request_id"),
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
                        "workflow_agent_failed request_id=%s company_name=%s "
                        "agent_name=%s status=%s error_code=%s "
                        "continue_on_error=%s error=%s"
                    ),
                    context.get("request_id"),
                    context.get("company_name"),
                    agent.name,
                    step.status,
                    step.error_code,
                    self._continue_on_error,
                    step.error,
                )

            progress_steps = list(state.get("steps", [])) + [asdict(step)]
            progress_summary = _summarize_steps(progress_steps)
            logger.info(
                (
                    "workflow_progress request_id=%s company_name=%s "
                    "completed_steps=%s success_steps=%s partial_steps=%s "
                    "failed_steps=%s fallback_steps=%s last_agent=%s last_status=%s"
                ),
                context.get("request_id"),
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
            if (
                agent.name == "industry_analyst"
                and self._financial_agent is not None
            ):
                continue
            node_names.append(agent.name)
        return node_names

    def _analysis_terminal_node_names(self) -> list[str]:
        node_names: list[str] = []
        for agent in self._parallel_agents:
            if (
                agent.name == "news_collector"
                and self._has_parallel_agent("risk_event")
            ):
                continue
            if (
                agent.name == "financial_analyst"
                and self._has_parallel_agent("industry_analyst")
            ):
                continue
            node_names.append(agent.name)
        return node_names

    def _connect_analysis_agents(self, builder: StateGraph) -> None:
        if self._has_parallel_agent("risk_event"):
            if self._news_agent is not None:
                builder.add_edge(self._news_agent.name, "risk_event")

        if self._has_parallel_agent("industry_analyst"):
            if self._financial_agent is not None:
                builder.add_edge(self._financial_agent.name, "industry_analyst")

    def _connect_sequential_agents(self, builder: StateGraph) -> None:
        if not self._sequential_agents:
            for terminal_name in self._analysis_terminal_node_names():
                builder.add_edge(terminal_name, END)
            return

        first_sequential = self._sequential_agents[0].name
        analysis_terminal_names = self._analysis_terminal_node_names()
        for terminal_name in analysis_terminal_names:
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


def _build_result(state: WorkflowState) -> dict[str, Any]:
    context = dict(state.get("context", {}))
    steps = list(state.get("steps", []))

    if context.get("company_found") is False:
        return {
            "status": "not_target",
            "code": context.get("workflow_code", "COMPANY_NOT_FOUND"),
            "message": context.get(
                "workflow_message",
                "대상 기업이 아닙니다.",
            ),
            "context": context,
            "steps": steps,
        }

    return {
        "status": _derive_status(steps),
        "context": context,
        "steps": steps,
    }


def _derive_status(steps: list[dict[str, Any]]) -> str:
    if not steps:
        return "not_started"
    ok_count = sum(1 for step in steps if step["ok"])
    if ok_count == len(steps):
        return "success"
    if ok_count == 0:
        return "failed"
    return "partial"


def _summarize_steps(steps: list[dict[str, Any]]) -> dict[str, int]:
    success_steps = sum(1 for step in steps if step.get("status") == "success")
    partial_steps = sum(1 for step in steps if step.get("status") == "partial")
    failed_steps = sum(1 for step in steps if step.get("status") == "failed")
    fallback_steps = sum(1 for step in steps if step.get("fallback_used") is True)
    return {
        "success": success_steps,
        "partial": partial_steps,
        "failed": failed_steps,
        "fallback": fallback_steps,
    }


async def _run_agent_step(agent: Agent, context: dict[str, Any]) -> StepResult:
    agent_name = getattr(agent, "name", agent.__class__.__name__)
    timeout_seconds = resolve_agent_timeout_seconds(context, agent_name)
    retry_attempts = resolve_agent_retry_attempts(context, agent_name)
    retry_backoff_seconds = resolve_agent_retry_backoff_seconds(context, agent_name)
    logger.info(
        (
            "workflow_agent_execution_config request_id=%s company_name=%s "
            "agent_name=%s timeout_seconds=%s retry_attempts=%s "
            "retry_backoff_seconds=%s"
        ),
        context.get("request_id"),
        context.get("company_name"),
        agent_name,
        timeout_seconds,
        retry_attempts,
        retry_backoff_seconds,
    )
    attempt = 0

    while attempt < retry_attempts:
        attempt += 1
        started_at = asyncio.get_running_loop().time()
        try:
            raw_output = await asyncio.wait_for(agent.run(context), timeout_seconds)
            if not isinstance(raw_output, dict):
                raise TypeError(
                    f"{agent_name}.run() 반환값은 dict여야 합니다. "
                    f"실제 타입: {type(raw_output).__name__}"
                )

            contract_output = build_agent_output(
                raw_output,
                latency_ms=int((asyncio.get_running_loop().time() - started_at) * 1000),
            )
            execution = extract_agent_execution(contract_output)
            return StepResult(
                agent_name=agent_name,
                ok=is_agent_step_ok(execution["status"]),
                status=execution["status"],
                error_code=execution["error_code"],
                fallback_used=execution["fallback_used"],
                latency_ms=execution["latency_ms"],
                output=extract_agent_business_output(contract_output),
                error=(
                    None
                    if is_agent_step_ok(execution["status"])
                    else execution["error_code"]
                ),
            )
        except Exception as exc:  # noqa: BLE001
            error_code = classify_agent_error(exc)
            if attempt < retry_attempts and should_retry_agent_error(exc):
                logger.warning(
                    (
                        "workflow_agent_retry request_id=%s company_name=%s "
                        "agent_name=%s attempt=%s max_attempts=%s "
                        "error_code=%s error=%s"
                    ),
                    context.get("request_id"),
                    context.get("company_name"),
                    agent_name,
                    attempt,
                    retry_attempts,
                    error_code,
                    exc,
                )
                await asyncio.sleep(retry_backoff_seconds * attempt)
                continue

            failure_output = build_agent_failure_output(
                error_code=error_code,
                latency_ms=int((asyncio.get_running_loop().time() - started_at) * 1000),
            )
            execution = extract_agent_execution(failure_output)
            return StepResult(
                agent_name=agent_name,
                ok=False,
                status=execution["status"],
                error_code=execution["error_code"],
                fallback_used=execution["fallback_used"],
                latency_ms=execution["latency_ms"],
                output=extract_agent_business_output(failure_output),
                error=str(exc),
            )

    failure_output = build_agent_failure_output(
        error_code="AGENT_EXECUTION_FAILED",
        latency_ms=0,
    )
    execution = extract_agent_execution(failure_output)
    return StepResult(
        agent_name=agent_name,
        ok=False,
        status=execution["status"],
        error_code=execution["error_code"],
        fallback_used=execution["fallback_used"],
        latency_ms=execution["latency_ms"],
        output={},
        error="알 수 없는 에이전트 실행 실패",
    )


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
    ]
