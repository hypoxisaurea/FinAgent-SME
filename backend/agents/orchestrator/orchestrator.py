from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

from agents.base import Agent
from agents.company_resolver import CompanyResolverAgent
from agents.decision import DecisionAgent
from agents.financial_analyst import FinancialAnalystAgent
from agents.industry_analyst import IndustryAnalystAgent
from agents.multimodal_document import MultiModalDocumentAgent
from agents.news_collector import NewsCollectorAgent
from agents.report import ReportAgent
from agents.risk_event import RiskEventAgent


@dataclass(slots=True)
class StepResult:
    """오케스트레이션 단일 단계 실행 결과."""

    agent_name: str
    ok: bool
    output: dict[str, Any]
    error: str | None = None


class WorkflowOrchestrator:
    """대상 기업 판별, 병렬 분석, 후속 심사 단계를 관리한다."""

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

    def _validate_agents(self) -> None:
        candidates = [
            *([self._resolver_agent] if self._resolver_agent is not None else []),
            *self._parallel_agents,
            *self._sequential_agents,
        ]
        for agent in candidates:
            if not isinstance(agent, Agent):
                raise TypeError(
                    f"Agent 프로토콜 미준수 객체가 포함되어 있습니다: {agent!r}"
                )

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        context: dict[str, Any] = dict(payload)
        steps: list[StepResult] = []

        if self._resolver_agent is not None:
            resolver_step = await _run_agent_step(self._resolver_agent, context)
            steps.append(resolver_step)
            if resolver_step.ok:
                context.update(resolver_step.output)
                if context.get("company_found") is False:
                    return {
                        "status": "not_target",
                        "code": context.get("workflow_code", "COMPANY_NOT_FOUND"),
                        "message": context.get(
                            "workflow_message",
                            "대상 기업이 아닙니다.",
                        ),
                        "context": context,
                        "steps": [asdict(step) for step in steps],
                    }
            elif not self._continue_on_error:
                return {
                    "status": _derive_status(steps),
                    "context": context,
                    "steps": [asdict(step) for step in steps],
                }

        parallel_steps = await self._run_parallel_agents(context)
        steps.extend(parallel_steps)
        for step in parallel_steps:
            if step.ok:
                context.update(step.output)

        if any(not step.ok for step in parallel_steps) and not self._continue_on_error:
            return {
                "status": _derive_status(steps),
                "context": context,
                "steps": [asdict(step) for step in steps],
            }

        for agent in self._sequential_agents:
            step = await _run_agent_step(agent, context)
            steps.append(step)
            if step.ok:
                context.update(step.output)
                continue
            if not self._continue_on_error:
                break

        return {
            "status": _derive_status(steps),
            "context": context,
            "steps": [asdict(step) for step in steps],
        }

    async def _run_parallel_agents(self, context: dict[str, Any]) -> list[StepResult]:
        if not self._parallel_agents:
            return []

        tasks = [
            _run_agent_step(agent, dict(context))
            for agent in self._parallel_agents
        ]
        return list(await asyncio.gather(*tasks))


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
      2. 병렬 분석 단계
         - NewsCollectorAgent   — 뉴스 수집
         - FinancialAnalystAgent
         - IndustryAnalystAgent
         - RiskEventAgent
         - MultiModalDocumentAgent (pdf_path 있을 때만)
      3. DecisionAgent        — 신용등급·승인 판단
      4. ReportAgent          — 최종 리포트 생성
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


def _derive_status(steps: list[StepResult]) -> str:
    if not steps:
        return "not_started"
    ok_count = sum(1 for step in steps if step.ok)
    if ok_count == len(steps):
        return "success"
    if ok_count == 0:
        return "failed"
    return "partial"


async def _run_agent_step(agent: Agent, context: dict[str, Any]) -> StepResult:
    try:
        output = await agent.run(context)
        if not isinstance(output, dict):
            raise TypeError(
                f"{agent.name}.run() 반환값은 dict여야 합니다. "
                f"실제 타입: {type(output).__name__}"
            )
        return StepResult(
            agent_name=agent.name,
            ok=True,
            output=output,
        )
    except Exception as exc:  # noqa: BLE001
        return StepResult(
            agent_name=getattr(agent, "name", agent.__class__.__name__),
            ok=False,
            output={},
            error=str(exc),
        )


def _build_parallel_agents(payload: dict[str, Any]) -> list[Agent]:
    parallel_agents: list[Agent] = [
        NewsCollectorAgent(),
        FinancialAnalystAgent(),
        IndustryAnalystAgent(),
        RiskEventAgent(),
    ]
    if payload.get("pdf_path"):
        parallel_agents.append(MultiModalDocumentAgent())
    return parallel_agents


def _build_sequential_agents() -> list[Agent]:
    return [
        DecisionAgent(),
        ReportAgent(),
    ]
