from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agents.base import Agent
from agents.collector import CollectorAgent
from agents.decision import DecisionAgent
from agents.multimodal_document import MultiModalDocumentAgent
from agents.risk_event import RiskEventAgent


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
            except Exception as exc:  # noqa: BLE001
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
    payload: dict[str, Any] | None = None,
    continue_on_error: bool = False,
) -> WorkflowOrchestrator:
    """신용심사 워크플로우 오케스트레이터 팩토리."""
    default_agents = agents if agents is not None else _build_default_agents(payload or {})
    return WorkflowOrchestrator(agents=default_agents, continue_on_error=continue_on_error)


async def run_credit_workflow(
    company_name: str,
    *,
    agents: list[Agent] | None = None,
    extra_payload: dict[str, Any] | None = None,
    continue_on_error: bool = False,
) -> dict[str, Any]:
    """멀티 에이전트 심사 파이프라인 진입점.

    기본 실행 순서:
      1. CollectorAgent       — DART·뉴스 데이터 수집
      2. RiskEventAgent       — 리스크 이벤트 탐지 (corp_code 필요)
      3. DecisionAgent        — 신용등급·승인 판단
      4. MultiModalDocumentAgent — pdf_path 있을 때만 추가
    """
    normalized_name = company_name.strip()
    if not normalized_name:
        raise ValueError("company_name은 비어 있을 수 없습니다.")

    payload: dict[str, Any] = {"company_name": normalized_name}
    if extra_payload:
        payload.update(extra_payload)

    orchestrator = create_credit_workflow(
        agents=agents,
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


def _build_default_agents(payload: dict[str, Any]) -> list[Agent]:
    """기본 에이전트 목록을 빌드한다.

    주의:
      RiskEventAgent는 payload에 corp_code가 있어야 정상 동작한다.
      corp_code가 없으면 RiskEventAgent 내부에서 빈 결과를 반환한다.
    """
    default_agents: list[Agent] = [
        CollectorAgent(),
        RiskEventAgent(),
        DecisionAgent(),
    ]
    if payload.get("pdf_path"):
        default_agents.append(MultiModalDocumentAgent())
    return default_agents
