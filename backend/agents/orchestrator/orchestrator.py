from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agents.base import Agent
from agents.collector import CollectorAgent
from agents.multimodal_document import MultiModalDocumentAgent


@dataclass(slots=True)
class StepResult:
    """오케스트레이션 단일 단계 실행 결과."""

    agent_name: str
    ok: bool
    output: dict[str, Any]
    error: str | None = None


class WorkflowOrchestrator:
    """여러 Agent를 순차 실행하고 컨텍스트를 누적한다."""

    def __init__(self, agents: list[Agent], *, continue_on_error: bool = False) -> None:
        self._agents = agents
        self._continue_on_error = continue_on_error
        self._validate_agents()

    def _validate_agents(self) -> None:
        if not self._agents:
            return
        for agent in self._agents:
            if not isinstance(agent, Agent):
                raise TypeError(f"Agent 프로토콜 미준수 객체가 포함되어 있습니다: {agent!r}")

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        context: dict[str, Any] = dict(payload)
        steps: list[StepResult] = []

        for agent in self._agents:
            try:
                output = await agent.run(context)
                if not isinstance(output, dict):
                    raise TypeError(
                        f"{agent.name}.run() 반환값은 dict여야 합니다. "
                        f"실제 타입: {type(output).__name__}"
                    )

                context.update(output)
                steps.append(
                    StepResult(
                        agent_name=agent.name,
                        ok=True,
                        output=output,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 오케스트레이터에서 단계 예외 집계
                steps.append(
                    StepResult(
                        agent_name=getattr(agent, "name", agent.__class__.__name__),
                        ok=False,
                        output={},
                        error=str(exc),
                    )
                )
                if not self._continue_on_error:
                    break

        return {
            "status": _derive_status(steps),
            "context": context,
            "steps": [asdict(step) for step in steps],
        }


def create_credit_workflow(
    agents: list[Agent] | None = None,
    *,
    continue_on_error: bool = False,
) -> WorkflowOrchestrator:
    """신용심사 워크플로우 오케스트레이터 팩토리.

    기본 워크플로우는 CollectorAgent와 MultiModalDocumentAgent를 순차 실행합니다.
    """
    default_agents = agents if agents is not None else [CollectorAgent(), MultiModalDocumentAgent()]
    return WorkflowOrchestrator(agents=default_agents, continue_on_error=continue_on_error)


async def run_credit_workflow(
    company_name: str,
    *,
    agents: list[Agent] | None = None,
    extra_payload: dict[str, Any] | None = None,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    """
    멀티 에이전트 심사 파이프라인 진입점.
    - 기본 입력 컨텍스트를 만들고
    - 등록된 에이전트를 순차 실행해
    - 통합 결과를 반환한다.

    extra_payload에는 멀티모달 문서 에이전트를 위한 "pdf_path"를 포함할 수 있습니다.
    """
    normalized_name = company_name.strip()
    if not normalized_name:
        raise ValueError("company_name은 비어 있을 수 없습니다.")

    payload: dict[str, Any] = {"company_name": normalized_name}
    if extra_payload:
        payload.update(extra_payload)

    orchestrator = create_credit_workflow(
        agents=agents,
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
