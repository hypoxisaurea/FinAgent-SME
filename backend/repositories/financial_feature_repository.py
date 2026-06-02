from __future__ import annotations

import logging
from typing import Any

from backend.infrastructure.db import FEATURES_TABLE_NAME
from backend.repositories.db_access import fetch_rows

logger = logging.getLogger(__name__)


def _normalize_corp_code(corp_code: str) -> str:
    return str(corp_code).zfill(8)


def get_financial_rows_by_corp_code(corp_code: str) -> list[dict[str, Any]]:
    """재무 피처 테이블에서 기업의 연도별 재무 데이터를 조회한다."""
    normalized_corp_code = _normalize_corp_code(corp_code)
    return fetch_rows(
        logger=logger,
        query=f"""
            SELECT
                LPAD(CAST(corp_code AS TEXT), 8, '0') AS corp_code,
                corp_name,
                CAST(stock_code AS TEXT) AS stock_code,
                year,
                avg_revenue_last_3y,
                total_assets,
                revenue,
                operating_income,
                net_income,
                total_assets_statement,
                total_liabilities,
                total_equity,
                created_at
            FROM {FEATURES_TABLE_NAME}
            WHERE LPAD(CAST(corp_code AS TEXT), 8, '0') = :corp_code
            ORDER BY year ASC
        """,
        params={"corp_code": normalized_corp_code},
        table_name=FEATURES_TABLE_NAME,
        error_message=f"{FEATURES_TABLE_NAME} 테이블 조회 중 오류가 발생했습니다.",
    )
