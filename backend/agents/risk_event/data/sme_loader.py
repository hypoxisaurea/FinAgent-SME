"""SME 데이터 로더

PostgreSQL에 저장된 기업 마스터 및 재무 피처 데이터를 조회한다.
"""

from __future__ import annotations

import logging
from typing import Any

from services.sme_repository import (
    get_all_corp_codes as get_all_corp_codes_from_db,
)
from services.sme_repository import (
    get_company_info_by_corp_code,
    get_financial_rows_by_corp_code,
    search_company_infos_by_name,
)

logger = logging.getLogger(__name__)


def get_financial_rows(corp_code: str) -> list[dict[str, Any]]:
    """특정 기업의 연도별 재무 데이터를 반환한다."""
    return get_financial_rows_by_corp_code(corp_code)


def get_company_info(corp_code: str) -> dict[str, Any] | None:
    """기업 마스터 테이블에서 기업 기본 정보를 반환한다."""
    return get_company_info_by_corp_code(corp_code)


def search_companies_by_name(keyword: str) -> list[dict[str, Any]]:
    """기업명 키워드로 후보 기업 목록을 반환한다."""
    return search_company_infos_by_name(keyword)


def get_all_corp_codes() -> list[str]:
    """전체 중소기업 corp_code 목록을 반환한다."""
    return get_all_corp_codes_from_db()


def reload_cache() -> None:
    """이전 CSV 캐시 호환용 no-op 함수."""
    logger.info("sme_loader_reload_cache_skipped backend=postgresql")
