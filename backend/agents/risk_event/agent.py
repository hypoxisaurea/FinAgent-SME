"""Risk Event Agent 구현체

base.py의 Agent Protocol을 준수한다.
  - name: str  (클래스 속성)
  - async run(payload) -> dict
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from backend.agents.risk_event.graph import run_risk_event_agent
from backend.common.contracts import (
    AGENT_PARTIAL_STATUS,
    AGENT_SUCCESS_STATUS,
    build_agent_output,
    elapsed_ms,
)

logger = logging.getLogger(__name__)


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
        started_at = perf_counter()
        logger.info(
            (
                "risk_event_agent_started company_name=%s corp_code=%s "
                "news_count=%s disclosure_count=%s court_count=%s"
            ),
            payload["company_name"],
            payload["corp_code"],
            len(payload.get("news_data", [])),
            len(payload.get("disclosure_data", [])),
            len(payload.get("court_data", [])),
        )
        result = await run_risk_event_agent(
            company_name=payload["company_name"],
            corp_code=payload["corp_code"],
            news_data=payload.get("news_data", []),
            disclosure_data=payload.get("disclosure_data", []),
            court_data=payload.get("court_data", []),
            request_id=payload.get("request_id"),
        )
        logger.info(
            (
                "risk_event_agent_finished company_name=%s corp_code=%s "
                "overall_risk_level=%s total_event_count=%s"
            ),
            payload["company_name"],
            payload["corp_code"],
            result.overall_risk_level.value,
            result.total_event_count,
        )
        result_payload = result.model_dump()
        fallback_used = bool(result_payload.get("processing_errors"))
        agent_status = AGENT_PARTIAL_STATUS if fallback_used else AGENT_SUCCESS_STATUS
        agent_error_code = "RISK_SIGNAL_PARTIAL" if fallback_used else "OK"
        return build_agent_output(
            result_payload,
            status=agent_status,
            error_code=agent_error_code,
            fallback_used=fallback_used,
            latency_ms=elapsed_ms(started_at),
        )
