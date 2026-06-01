from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect, text

from agents.company_registry.tools import (
    FEATURES_TABLE_NAME,
    SME_LIST_TABLE_NAME,
    create_db_engine,
)

logger = logging.getLogger(__name__)


def _normalize_corp_code(corp_code: str) -> str:
    return str(corp_code).zfill(8)


def _fetch_rows(
    *,
    query: str,
    params: dict[str, Any],
    table_name: str,
) -> list[dict[str, Any]]:
    engine = create_db_engine()
    try:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            logger.info("sme_repository_table_missing table=%s", table_name)
            return []

        with engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()

        return [dict(row) for row in rows]
    except Exception as exc:  # noqa: BLE001
        logger.exception("sme_repository_query_failed table=%s", table_name)
        raise RuntimeError(
            f"{table_name} 테이블 조회 중 오류가 발생했습니다."
        ) from exc
    finally:
        engine.dispose()


def get_financial_rows_by_corp_code(corp_code: str) -> list[dict[str, Any]]:
    """재무 피처 테이블에서 기업의 연도별 재무 데이터를 조회한다."""
    normalized_corp_code = _normalize_corp_code(corp_code)
    query = f"""
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
    """
    return _fetch_rows(
        query=query,
        params={"corp_code": normalized_corp_code},
        table_name=FEATURES_TABLE_NAME,
    )


def get_company_info_by_corp_code(corp_code: str) -> dict[str, Any] | None:
    """기업 마스터 테이블에서 단일 기업 정보를 조회한다."""
    normalized_corp_code = _normalize_corp_code(corp_code)
    query = f"""
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
    """
    rows = _fetch_rows(
        query=query,
        params={"corp_code": normalized_corp_code},
        table_name=SME_LIST_TABLE_NAME,
    )
    return rows[0] if rows else None


def search_company_infos_by_name(keyword: str) -> list[dict[str, Any]]:
    """기업명을 기준으로 기업 마스터 후보 목록을 조회한다."""
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return []

    query = f"""
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
    """
    return _fetch_rows(
        query=query,
        params={"keyword": f"%{normalized_keyword}%"},
        table_name=SME_LIST_TABLE_NAME,
    )


def get_all_corp_codes() -> list[str]:
    """기업 마스터 테이블의 전체 corp_code 목록을 반환한다."""
    query = f"""
        SELECT DISTINCT LPAD(CAST(corp_code AS TEXT), 8, '0') AS corp_code
        FROM {SME_LIST_TABLE_NAME}
        ORDER BY corp_code ASC
    """
    rows = _fetch_rows(query=query, params={}, table_name=SME_LIST_TABLE_NAME)
    return [str(row["corp_code"]) for row in rows]
