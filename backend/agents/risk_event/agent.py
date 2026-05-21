"""Risk Event Agent 구현체

base.py의 Agent Protocol을 준수한다.
  - name: str  (클래스 속성)
  - async run(payload) -> dict
"""

from __future__ import annotations

from typing import Any

from .graph import run_risk_event_agent


class RiskEventAgent:
    """뉴스·공시·법원·재무 데이터 기반 리스크 이벤트 탐지 에이전트."""

    name: str = "risk_event"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Risk Event Agent 실행.

        Args:
            payload:
                company_name    (str)        : 기업명
                corp_code       (str)        : DART 고유번호
                news_data       (list[dict]) : 뉴스 원문 목록
                disclosure_data (list[dict]) : 공시 목록
                court_data      (list[dict]) : 법원 경매·파산 공고 목록

        Returns:
            RiskEventResult.model_dump()
        """
        result = await run_risk_event_agent(
            company_name    = payload["company_name"],
            corp_code       = payload["corp_code"],
            news_data       = payload.get("news_data", []),
            disclosure_data = payload.get("disclosure_data", []),
            court_data      = payload.get("court_data", []),
        )
        return result.model_dump()
