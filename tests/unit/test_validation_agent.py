from __future__ import annotations

import asyncio
from datetime import date

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
                "corp_name": "테스트기업",
                "corp_code": "00000001",
                "decision": "approve",
                "credit_grade": "A",
                "decision_confidence": 0.92,
                "decision_reasons": [
                    "매출 성장세가 양호합니다.",
                    "재무 안정성이 우수합니다.",
                    "주요 리스크 이벤트가 없습니다.",
                    "초과 근거는 리포트에 포함되지 않아야 합니다.",
                ],
                "recommended_limit": 1000000,
                "explanation": {
                    "summary": "정상 요약",
                    "recommendation": "정상 권고",
                },
                "report": {
                    "company_name": "테스트기업",
                    "corp_name": "테스트기업",
                    "corp_code": "00000001",
                    "generated_at": date.today().isoformat(),
                    "decision": "approve",
                    "credit_grade": "A",
                    "confidence": 0.92,
                    "recommended_limit": 1000000,
                    "summary": "정상 요약",
                    "key_risks": [
                        "매출 성장세가 양호합니다.",
                        "재무 안정성이 우수합니다.",
                        "주요 리스크 이벤트가 없습니다.",
                    ],
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
                "corp_name": "테스트기업",
                "corp_code": "00000001",
                "decision": "reject",
                "credit_grade": "E",
                "decision_confidence": 0.78,
                "decision_reasons": [
                    "부채 부담이 과도합니다.",
                    "현금흐름이 불안정합니다.",
                ],
                "recommended_limit": 5000,
                "explanation": {
                    "summary": "거절 요약",
                    "recommendation": "거절 권고",
                },
                "report": {
                    "company_name": "테스트기업",
                    "corp_name": "테스트기업",
                    "corp_code": "00000001",
                    "generated_at": date.today().isoformat(),
                    "decision": "reject",
                    "credit_grade": "E",
                    "confidence": 0.78,
                    "recommended_limit": 5000,
                    "summary": "거절 요약",
                    "key_risks": [
                        "부채 부담이 과도합니다.",
                        "현금흐름이 불안정합니다.",
                    ],
                    "recommendation": "거절 권고",
                },
            }
        )
    )

    assert result["status"] == "partial"
    assert result["error_code"] == "VALIDATION_WARNING"
    assert result["validation_result"]["validation_passed"] is False
    assert "reject_limit_rule" in result["validation_result"]["failed_checks"]


def test_validation_agent_detects_report_field_mismatches(
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
                "request_id": "req-val-3",
                "company_name": "테스트기업",
                "corp_name": "테스트기업",
                "corp_code": "00000001",
                "decision": "review",
                "credit_grade": "C",
                "decision_confidence": 0.61,
                "decision_reasons": [
                    "단기 차입금 비중이 높습니다.",
                    "산업 업황이 둔화 중입니다.",
                    "추가 담보 검토가 필요합니다.",
                ],
                "recommended_limit": 300000000,
                "explanation": {
                    "summary": "조건부 검토가 필요합니다.",
                    "recommendation": "추가 자료 확보 후 판단을 권고합니다.",
                },
                "report": {
                    "company_name": "테스트기업",
                    "corp_name": "테스트기업",
                    "corp_code": "00000001",
                    "generated_at": date.today().isoformat(),
                    "decision": "review",
                    "credit_grade": "C",
                    "confidence": 0.55,
                    "recommended_limit": 100000000,
                    "summary": "요약이 바뀌었습니다.",
                    "key_risks": ["다른 리스크"],
                    "recommendation": "다른 권고입니다.",
                },
            }
        )
    )

    assert result["status"] == "partial"
    assert result["validation_result"]["validation_passed"] is False
    assert "report_confidence_matches" in result["validation_result"]["failed_checks"]
    assert "report_recommended_limit_matches" in result["validation_result"]["failed_checks"]
    assert "report_key_risks_matches" in result["validation_result"]["failed_checks"]
    assert "report_summary_matches_explanation" in result["validation_result"]["failed_checks"]
    assert "report_recommendation_matches_explanation" in result["validation_result"]["failed_checks"]
