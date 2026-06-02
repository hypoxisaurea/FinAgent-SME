from __future__ import annotations

import logging
from typing import Any

from backend.infrastructure.db import SME_LIST_TABLE_NAME
from backend.repositories.db_access import fetch_rows

logger = logging.getLogger(__name__)


def _normalize_corp_code(corp_code: str) -> str:
    return str(corp_code).zfill(8)


def find_company_row_by_name(company_name: str) -> dict[str, Any] | None:
    """기업명을 기준으로 기업 마스터 단일 행을 조회한다."""
    normalized_name = company_name.strip()
    if not normalized_name:
        raise ValueError("company_name은 비어 있을 수 없습니다.")

    rows = fetch_rows(
        logger=logger,
        query=f"""
            SELECT corp_code, corp_name
            FROM {SME_LIST_TABLE_NAME}
            WHERE corp_name = :company_name
            ORDER BY created_at DESC NULLS LAST, corp_code ASC
            LIMIT 1
        """,
        params={"company_name": normalized_name},
        table_name=SME_LIST_TABLE_NAME,
        error_message="기업 마스터 조회 중 오류가 발생했습니다.",
        missing_table_error_message=(
            f"기업 마스터 테이블이 존재하지 않습니다: {SME_LIST_TABLE_NAME}"
        ),
    )
    return rows[0] if rows else None


def get_company_info_by_corp_code(corp_code: str) -> dict[str, Any] | None:
    """기업 마스터 테이블에서 단일 기업 정보를 조회한다."""
    normalized_corp_code = _normalize_corp_code(corp_code)
    rows = fetch_rows(
        logger=logger,
        query=f"""
            SELECT
                LPAD(CAST(corp_code AS TEXT), 8, '0') AS corp_code,
                corp_name,
                CAST(stock_code AS TEXT) AS stock_code,
                avg_revenue_last_3y,
                total_assets,
                created_at
            FROM {SME_LIST_TABLE_NAME}
            WHERE LPAD(CAST(corp_code AS TEXT), 8, '0') = :corp_code
            ORDER BY created_at DESC NULLS LAST
            LIMIT 1
        """,
        params={"corp_code": normalized_corp_code},
        table_name=SME_LIST_TABLE_NAME,
        error_message=f"{SME_LIST_TABLE_NAME} 테이블 조회 중 오류가 발생했습니다.",
    )
    return rows[0] if rows else None


def search_company_infos_by_name(keyword: str) -> list[dict[str, Any]]:
    """기업명을 기준으로 기업 마스터 후보 목록을 조회한다."""
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return []

    return fetch_rows(
        logger=logger,
        query=f"""
            SELECT DISTINCT
                LPAD(CAST(corp_code AS TEXT), 8, '0') AS corp_code,
                corp_name,
                CAST(stock_code AS TEXT) AS stock_code,
                avg_revenue_last_3y,
                total_assets,
                created_at
            FROM {SME_LIST_TABLE_NAME}
            WHERE corp_name ILIKE :keyword
            ORDER BY corp_name ASC, corp_code ASC
        """,
        params={"keyword": f"%{normalized_keyword}%"},
        table_name=SME_LIST_TABLE_NAME,
        error_message=f"{SME_LIST_TABLE_NAME} 테이블 조회 중 오류가 발생했습니다.",
    )


def get_all_corp_codes() -> list[str]:
    """기업 마스터 테이블의 전체 corp_code 목록을 반환한다."""
    rows = fetch_rows(
        logger=logger,
        query=f"""
            SELECT DISTINCT LPAD(CAST(corp_code AS TEXT), 8, '0') AS corp_code
            FROM {SME_LIST_TABLE_NAME}
            ORDER BY corp_code ASC
        """,
        params={},
        table_name=SME_LIST_TABLE_NAME,
        error_message=f"{SME_LIST_TABLE_NAME} 테이블 조회 중 오류가 발생했습니다.",
    )
    return [str(row["corp_code"]) for row in rows]
