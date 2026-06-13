from __future__ import annotations

import asyncio
from typing import Any

from backend.agents.orchestrator.step_runner import run_agent_step
from pydantic import BaseModel, ConfigDict


class _InputContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    company_name: str
    corp_code: str


class _OutputContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str


class _ValidatingAgent:
    name = "validating_agent"
    input_model = _InputContract
    output_model = _OutputContract

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"decision": f"{payload['company_name']}:{payload['corp_code']}"}


class _BadOutputAgent(_ValidatingAgent):
    name = "bad_output_agent"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"recommended_limit": 1000}


def test_run_agent_step_returns_invalid_input_for_input_contract_violation() -> None:
    step = asyncio.run(
        run_agent_step(
            _ValidatingAgent(),
            {
                "company_name": "테스트기업",
            },
        )
    )

    assert step.ok is False
    assert step.status == "failed"
    assert step.error_code == "INVALID_INPUT"
    assert "input contract validation failed" in (step.error or "")


def test_run_agent_step_returns_invalid_output_for_output_contract_violation() -> None:
    step = asyncio.run(
        run_agent_step(
            _BadOutputAgent(),
            {
                "company_name": "테스트기업",
                "corp_code": "00123456",
            },
        )
    )

    assert step.ok is False
    assert step.status == "failed"
    assert step.error_code == "INVALID_OUTPUT"
    assert "output contract validation failed" in (step.error or "")


def test_run_agent_step_normalizes_validated_input_and_output() -> None:
    step = asyncio.run(
        run_agent_step(
            _ValidatingAgent(),
            {
                "company_name": "테스트기업",
                "corp_code": "123456",
                "request_id": "req-contract",
            },
        )
    )

    assert step.ok is True
    assert step.status == "success"
    assert step.output == {"decision": "테스트기업:123456"}
