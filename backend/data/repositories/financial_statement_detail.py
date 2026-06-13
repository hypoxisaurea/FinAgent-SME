from __future__ import annotations

import logging
from typing import Any

from backend.data.db import STATEMENT_DETAILS_TABLE_NAME
from backend.data.repositories.db_access import fetch_rows

logger = logging.getLogger(__name__)


def _normalize_corp_code(corp_code: str) -> str:
    return str(corp_code).zfill(8)


def get_statement_detail_rows_by_corp_code(corp_code: str) -> list[dict[str, Any]]:
    """심사용 상세 재무 테이블에서 기업의 연도별 재무 스냅샷을 조회한다."""
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
                current_assets,
                current_liabilities,
                total_assets_statement,
                total_liabilities,
                total_equity,
                retained_earnings,
                inventory,
                accounts_receivable,
                accounts_payable,
                short_term_borrowings,
                current_portion_long_term_borrowings,
                long_term_borrowings,
                bonds,
                tangible_assets,
                revenue,
                cost_of_goods_sold,
                operating_income,
                net_income,
                interest_expense,
                operating_cashflow,
                capital_expenditure,
                audit_opinion,
                is_external_audit,
                created_at
            FROM {STATEMENT_DETAILS_TABLE_NAME}
            WHERE LPAD(CAST(corp_code AS TEXT), 8, '0') = :corp_code
            ORDER BY year ASC
        """,
        params={"corp_code": normalized_corp_code},
        table_name=STATEMENT_DETAILS_TABLE_NAME,
        error_message=(
            f"{STATEMENT_DETAILS_TABLE_NAME} 테이블 조회 중 오류가 발생했습니다."
        ),
    )
