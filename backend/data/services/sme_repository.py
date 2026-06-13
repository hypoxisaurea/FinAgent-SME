from __future__ import annotations

import logging
from typing import Any

from backend.data.repositories.company_master import (
    get_all_corp_codes as get_all_corp_codes_from_repository,
)
from backend.data.repositories.company_master import (
    get_company_info_by_corp_code as get_company_info_by_corp_code_from_repository,
)
from backend.data.repositories.company_master import (
    search_company_infos_by_name as search_company_infos_by_name_from_repository,
)
from backend.data.repositories.financial_feature import (
    get_financial_rows_by_corp_code as get_financial_rows_by_corp_code_from_repository,
)
from backend.data.repositories.financial_statement_detail import (
    get_statement_detail_rows_by_corp_code as get_statement_detail_rows_by_corp_code_from_repository,
)

logger = logging.getLogger(__name__)


def _normalize_corp_code(corp_code: str) -> str:
    return str(corp_code).zfill(8)


def get_financial_rows_by_corp_code(corp_code: str) -> list[dict[str, Any]]:
    """재무 피처 테이블에서 기업의 연도별 재무 데이터를 조회한다."""
    return get_financial_rows_by_corp_code_from_repository(
        _normalize_corp_code(corp_code)
    )


def get_statement_detail_rows_by_corp_code(corp_code: str) -> list[dict[str, Any]]:
    """심사용 상세 재무 테이블에서 기업의 연도별 재무 스냅샷을 조회한다."""
    return get_statement_detail_rows_by_corp_code_from_repository(
        _normalize_corp_code(corp_code)
    )


def get_company_info_by_corp_code(corp_code: str) -> dict[str, Any] | None:
    """기업 마스터 테이블에서 단일 기업 정보를 조회한다."""
    return get_company_info_by_corp_code_from_repository(_normalize_corp_code(corp_code))


def search_company_infos_by_name(keyword: str) -> list[dict[str, Any]]:
    """기업명을 기준으로 기업 마스터 후보 목록을 조회한다."""
    return search_company_infos_by_name_from_repository(keyword)


def get_all_corp_codes() -> list[str]:
    """기업 마스터 테이블의 전체 corp_code 목록을 반환한다."""
    return get_all_corp_codes_from_repository()
