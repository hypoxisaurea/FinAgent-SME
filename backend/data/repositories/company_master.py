from __future__ import annotations

import logging
from typing import Any

from backend.data.db import COMPANY_PROFILE_TABLE_NAME, SME_LIST_TABLE_NAME
from backend.data.repositories.db_access import fetch_rows

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
            SELECT *
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
    if not rows:
        return None
    row = rows[0]
    return _merge_company_profile(row)


def get_company_info_by_corp_code(corp_code: str) -> dict[str, Any] | None:
    """기업 마스터 테이블에서 단일 기업 정보를 조회한다."""
    normalized_corp_code = _normalize_corp_code(corp_code)
    rows = fetch_rows(
        logger=logger,
        query=f"""
            SELECT *
            FROM {SME_LIST_TABLE_NAME}
            WHERE LPAD(CAST(corp_code AS TEXT), 8, '0') = :corp_code
            ORDER BY created_at DESC NULLS LAST
            LIMIT 1
        """,
        params={"corp_code": normalized_corp_code},
        table_name=SME_LIST_TABLE_NAME,
        error_message=f"{SME_LIST_TABLE_NAME} 테이블 조회 중 오류가 발생했습니다.",
    )
    if not rows:
        return None
    row = rows[0]
    return _merge_company_profile(row)


def search_company_infos_by_name(keyword: str) -> list[dict[str, Any]]:
    """기업명을 기준으로 기업 마스터 후보 목록을 조회한다."""
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return []

    rows = fetch_rows(
        logger=logger,
        query=f"""
            SELECT DISTINCT *
            FROM {SME_LIST_TABLE_NAME}
            WHERE corp_name ILIKE :keyword
            ORDER BY corp_name ASC, corp_code ASC
        """,
        params={"keyword": f"%{normalized_keyword}%"},
        table_name=SME_LIST_TABLE_NAME,
        error_message=f"{SME_LIST_TABLE_NAME} 테이블 조회 중 오류가 발생했습니다.",
    )
    return [_merge_company_profile(row) for row in rows]


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


def _merge_company_profile(base_row: dict[str, Any]) -> dict[str, Any]:
    corp_code = str(base_row["corp_code"]).zfill(8)
    profile_rows = fetch_rows(
        logger=logger,
        query=f"""
            SELECT *
            FROM {COMPANY_PROFILE_TABLE_NAME}
            WHERE LPAD(CAST(corp_code AS TEXT), 8, '0') = :corp_code
            ORDER BY created_at DESC NULLS LAST
            LIMIT 1
        """,
        params={"corp_code": corp_code},
        table_name=COMPANY_PROFILE_TABLE_NAME,
        error_message=f"{COMPANY_PROFILE_TABLE_NAME} 테이블 조회 중 오류가 발생했습니다.",
    )
    if not profile_rows:
        return base_row

    merged = dict(base_row)
    for key, value in profile_rows[0].items():
        if key == "corp_code":
            continue
        if value is not None and str(value).strip():
            merged[key] = value
    return merged
