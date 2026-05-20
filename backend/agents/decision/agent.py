"""Decision Agent 구현체

base.py의 Agent Protocol을 준수한다.
  - name: str  (클래스 속성)
  - async run(payload) -> dict
"""

from __future__ import annotations

import logging
from typing import Any

from .graph import run_decision_agent

logger = logging.getLogger(__name__)


class DecisionAgent:
    """재무·리스크 데이터 종합 기반 신용 등급 산출 및 승인 판단 에이전트."""

    name: str = "decision"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Decision Agent 실행.

        Args:
            payload:
                company_name         (str)         : 기업명
                corp_code            (str)         : DART 고유번호
                --- RiskEventAgent 출력 (자동 누적) ---
                overall_risk_level   (str)         : critical|high|medium|low
                critical_count       (int)         : CRITICAL 이벤트 수
                high_count           (int)         : HIGH 이벤트 수
                medium_count         (int)         : MEDIUM 이벤트 수
                low_count            (int)         : LOW 이벤트 수
                latest_debt_ratio    (float|None)  : 최신 부채비율
                latest_op_margin     (float|None)  : 최신 영업이익률
                is_net_income_negative (bool)      : 당기순손실 여부
                --- FinancialAnalyst 출력 (선택) ---
                grade_cap            (str|None)    : 재무 등급 상한 (예: "BB+")
                --- 재무 데이터 (선택) ---
                total_assets         (float|None)  : 총자산
                revenue              (float|None)  : 매출액
                avg_revenue_last_3y  (float|None)  : 최근 3개년 평균 매출

        Returns:
            DecisionOutput.model_dump()
        """
        company_name = payload.get("company_name", "unknown")
        logger.info("decision_agent_started company=%s", company_name)

        output = await run_decision_agent(payload)

        if output is None:
            logger.error("decision_agent_failed company=%s output=None", company_name)
            return {
                "decision_output": None,
                "decision_error":  "Decision Agent 실행 실패",
            }

        logger.info(
            "decision_agent_finished company=%s grade=%s decision=%s",
            company_name,
            output.grade.value,
            output.decision.value,
        )

        result = output.model_dump()

        # Orchestrator·Report Agent가 바로 참조할 수 있도록 최상위 키로 노출
        result["decision"]            = output.decision.value
        result["credit_grade"]        = output.grade.value
        result["credit_score"]        = output.grade_score
        result["decision_confidence"] = output.confidence
        result["decision_reasons"]    = output.reasons
        result["recommended_limit"]   = output.recommended_limit

        return result