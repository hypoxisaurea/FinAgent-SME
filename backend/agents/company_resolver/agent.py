from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from backend.common.agent import Agent
from backend.common.contracts import build_agent_output, elapsed_ms
from backend.data.services.company_lookup import find_company_by_name

logger = logging.getLogger(__name__)


class CompanyResolverAgent(Agent):
    """대상 기업 여부를 판별하고 식별 정보를 확보하는 에이전트."""

    name = "company_resolver"

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """기업명을 기준으로 기업 마스터를 조회한다."""
        started_at = perf_counter()
        company_name = str(payload.get("company_name", "")).strip()
        if not company_name:
            raise ValueError("company_name은 비어 있을 수 없습니다.")

        result = find_company_by_name(company_name)
        if result is None:
            logger.info("company_resolver_not_target company_name=%s", company_name)
            return build_agent_output(
                {
                    "company_found": False,
                    "workflow_status": "not_target",
                    "workflow_code": "COMPANY_NOT_FOUND",
                    "workflow_message": "대상 기업이 아닙니다.",
                    "company_resolution": {
                        "matched": False,
                        "query": company_name,
                    },
                },
                latency_ms=elapsed_ms(started_at),
            )

        logger.info(
            "company_resolver_matched company_name=%s corp_code=%s corp_name=%s",
            company_name,
            result.corp_code,
            result.corp_name,
        )
        return build_agent_output(
                {
                    "company_found": True,
                    "corp_code": result.corp_code,
                    "corp_name": result.corp_name,
                    "company_profile": result.company_profile,
                    "company_resolution": {
                        "matched": True,
                        "query": company_name,
                        "corp_code": result.corp_code,
                        "corp_name": result.corp_name,
                },
            },
            latency_ms=elapsed_ms(started_at),
        )
