from __future__ import annotations

import asyncio

from backend.agents.validation.agent import ValidationAgent


def test_validation_agent_returns_success_for_consistent_result(
    monkeypatch,
) -> None:
    scored: list[tuple[str, float | int | str, str]] = []

    def fake_score_current_trace(
        *,
        name: str,
        value: float | int | str,
        data_type: str,
        comment: str | None = None,
    ) -> None:
        scored.append((name, value, data_type))

    monkeypatch.setattr(
        "backend.agents.validation.agent.score_current_trace",
        fake_score_current_trace,
    )

    result = asyncio.run(
        ValidationAgent().run(
            {
                "request_id": "req-val-1",
                "company_name": "테스트기업",
                "decision": "approve",
                "credit_grade": "A",
                "recommended_limit": 1000000,
                "report": {
                    "company_name": "테스트기업",
                    "decision": "approve",
                    "credit_grade": "A",
                    "summary": "정상 요약",
                    "recommendation": "정상 권고",
                },
            }
        )
    )

    assert result["status"] == "success"
    assert result["validation_result"]["validation_passed"] is True
    assert result["validation_result"]["pass_rate"] == 1.0
    assert {name for name, _, _ in scored} == {
        "validation_pass_rate",
        "workflow_contract_valid",
        "failed_check_count",
    }


def test_validation_agent_returns_partial_for_inconsistent_reject_limit(
    monkeypatch,
) -> None:
    def fake_score_current_trace(
        *,
        name: str,
        value: float | int | str,
        data_type: str,
        comment: str | None = None,
    ) -> None:
        return None

    monkeypatch.setattr(
        "backend.agents.validation.agent.score_current_trace",
        fake_score_current_trace,
    )

    result = asyncio.run(
        ValidationAgent().run(
            {
                "request_id": "req-val-2",
                "company_name": "테스트기업",
                "decision": "reject",
                "credit_grade": "E",
                "recommended_limit": 5000,
                "report": {
                    "company_name": "테스트기업",
                    "decision": "reject",
                    "credit_grade": "E",
                    "summary": "거절 요약",
                    "recommendation": "거절 권고",
                },
            }
        )
    )

    assert result["status"] == "partial"
    assert result["error_code"] == "VALIDATION_WARNING"
    assert result["validation_result"]["validation_passed"] is False
    assert "reject_limit_rule" in result["validation_result"]["failed_checks"]
