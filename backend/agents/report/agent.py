from __future__ import annotations

import logging
from datetime import date
from time import perf_counter
from typing import Any

from backend.common.agent import Agent
from backend.common.contracts import build_agent_output, elapsed_ms

logger = logging.getLogger(__name__)


class ReportAgent(Agent):
    """심사 결과를 최종 리포트 형태로 정리하는 에이전트."""

    name = "report"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Decision 결과와 중간 분석 결과를 리포트로 정리한다."""
        started_at = perf_counter()
        decision = payload.get("decision")
        credit_grade = payload.get("credit_grade")
        decision_reasons = payload.get("decision_reasons", [])
        explanation = payload.get("explanation")
        summary_fallback_used = not (
            isinstance(explanation, dict) and explanation.get("summary")
        )
        recommendation_fallback_used = not (
            isinstance(explanation, dict) and explanation.get("recommendation")
        )
        fallback_used = summary_fallback_used or recommendation_fallback_used

        report = {
            "company_name": payload.get("company_name"),
            "corp_name": payload.get("corp_name"),
            "corp_code": payload.get("corp_code"),
            "generated_at": date.today().isoformat(),
            "decision": decision,
            "credit_grade": credit_grade,
            "confidence": payload.get("decision_confidence"),
            "recommended_limit": payload.get("recommended_limit"),
            "summary": (
                explanation.get("summary")
                if isinstance(explanation, dict)
                else None
            ) or _build_summary(payload),
            "key_risks": decision_reasons[:3],
            "recommendation": (
                explanation.get("recommendation")
                if isinstance(explanation, dict)
                else None
            ) or _build_recommendation(payload),
        }

        logger.info(
            "report_generated company=%s decision=%s grade=%s",
            payload.get("company_name", "unknown"),
            decision,
            credit_grade,
        )
        return build_agent_output(
            {"report": report},
            fallback_used=fallback_used,
            error_code="REPORT_FALLBACK_USED" if fallback_used else "OK",
            latency_ms=elapsed_ms(started_at),
        )


def _build_summary(payload: dict[str, Any]) -> str:
    company_name = payload.get("company_name", "대상 기업")
    decision = payload.get("decision", "unknown")
    credit_grade = payload.get("credit_grade", "N/A")
    overall_risk_level = payload.get("overall_risk_level", "unknown")
    return (
        f"{company_name}의 심사 결과는 {decision}이며, "
        f"신용등급은 {credit_grade}입니다. "
        f"통합 리스크 수준은 {overall_risk_level}로 평가되었습니다."
    )


def _build_recommendation(payload: dict[str, Any]) -> str:
    if payload.get("decision") == "approve":
        return "승인 조건으로 후속 모니터링을 권고합니다."
    if payload.get("decision") == "review":
        return "추가 자료 검토 후 조건부 승인 여부를 판단하는 것을 권고합니다."
    return "보수적 심사 관점에서 거절 또는 재심사 보류를 권고합니다."
