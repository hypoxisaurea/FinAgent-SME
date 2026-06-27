from __future__ import annotations

import logging
from typing import Any

from backend.data.db import STATEMENT_DETAILS_TABLE_NAME
from backend.data.repositories import db_access

logger = logging.getLogger(__name__)

_STATEMENT_DETAIL_SELECT_COLUMNS = [
    "corp_name",
    "year",
    "avg_revenue_last_3y",
    "current_assets",
    "current_liabilities",
    "total_assets_statement",
    "total_liabilities",
    "total_equity",
    "retained_earnings",
    "inventory",
    "accounts_receivable",
    "accounts_payable",
    "short_term_borrowings",
    "current_portion_long_term_borrowings",
    "long_term_borrowings",
    "bonds",
    "tangible_assets",
    "revenue",
    "cost_of_goods_sold",
    "operating_income",
    "net_income",
    "interest_expense",
    "interest_expense_source_account",
    "interest_expense_quality",
    "operating_cashflow",
    "capital_expenditure",
    "audit_opinion",
    "is_external_audit",
    "created_at",
]


def _normalize_corp_code(corp_code: str) -> str:
    return str(corp_code).zfill(8)


def get_statement_detail_rows_by_corp_code(corp_code: str) -> list[dict[str, Any]]:
    """심사용 상세 재무 테이블에서 기업의 연도별 재무 스냅샷을 조회한다."""
    normalized_corp_code = _normalize_corp_code(corp_code)
    select_columns = _build_statement_detail_select_columns()
    return db_access.fetch_rows(
        logger=logger,
        query=f"""
            SELECT
                LPAD(CAST(corp_code AS TEXT), 8, '0') AS corp_code,
                {select_columns}
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


def _build_statement_detail_select_columns() -> str:
    """실제 DB 스키마에 맞춰 상세 재무 SELECT 컬럼 목록을 만든다."""
    engine = db_access.create_db_engine()
    try:
        inspector = db_access.inspect(engine)
        if not inspector.has_table(STATEMENT_DETAILS_TABLE_NAME):
            return _default_statement_detail_select_columns()
        existing_columns = {
            column["name"]
            for column in inspector.get_columns(STATEMENT_DETAILS_TABLE_NAME)
        }
    finally:
        engine.dispose()

    expressions = [_column_expression("stock_code", existing_columns, cast_text=True)]
    expressions.extend(
        _column_expression(column, existing_columns)
        for column in _STATEMENT_DETAIL_SELECT_COLUMNS
    )
    return ",\n                ".join(expressions)


def _default_statement_detail_select_columns() -> str:
    expressions = [_column_expression("stock_code", {"stock_code"}, cast_text=True)]
    expressions.extend(_STATEMENT_DETAIL_SELECT_COLUMNS)
    return ",\n                ".join(expressions)


def _column_expression(
    column: str,
    existing_columns: set[str],
    *,
    cast_text: bool = False,
) -> str:
    if column not in existing_columns:
        return f"NULL AS {column}"
    if cast_text:
        return f"CAST({column} AS TEXT) AS {column}"
    return column
