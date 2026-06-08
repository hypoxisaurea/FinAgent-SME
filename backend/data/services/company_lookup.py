from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.data.repositories.company_master import find_company_row_by_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompanyLookupResult:
    """기업 마스터 조회 결과."""

    corp_code: str
    corp_name: str
    company_profile: dict[str, Any]


PROFILE_FIELD_MAP = {
    "stock_code": "stock_code",
    "corp_cls": "corp_cls",
    "stock_name": "stock_name",
    "ceo_name": "ceo_name",
    "address": "address",
    "homepage_url": "homepage_url",
    "ir_url": "ir_url",
    "phone_number": "phone_number",
    "fax_number": "fax_number",
    "industry_code": "industry_code",
    "established_date": "established_date",
    "settlement_month": "settlement_month",
}


def build_company_profile(row: dict[str, Any]) -> dict[str, Any]:
    """기업 마스터 row에서 리포트용 기업개황 프로필을 생성한다."""
    has_profile_fields = any(
        row.get(source_key) is not None and str(row.get(source_key)).strip()
        for source_key in PROFILE_FIELD_MAP.values()
    )
    profile = {
        "corp_code": str(row["corp_code"]).zfill(8),
        "corp_name": str(row["corp_name"]),
        "source": "company_profiles" if has_profile_fields else "sme_list",
    }
    for target_key, source_key in PROFILE_FIELD_MAP.items():
        value = row.get(source_key)
        if value is not None and str(value).strip():
            profile[target_key] = str(value).strip()
    return profile


def find_company_by_name(company_name: str) -> CompanyLookupResult | None:
    """기업 마스터 테이블에서 기업명을 기준으로 회사를 조회한다.

    Args:
        company_name: 프론트엔드에서 전달한 검색 기업명

    Returns:
        조회된 기업의 `corp_code`, `corp_name`. 없으면 `None`.

    Raises:
        RuntimeError: 기업 마스터 테이블이 없거나 DB 조회에 실패한 경우
    """
    normalized_name = company_name.strip()
    if not normalized_name:
        raise ValueError("company_name은 비어 있을 수 없습니다.")

    try:
        row = find_company_row_by_name(normalized_name)
        if row is None:
            logger.info("company_lookup_not_found company_name=%s", normalized_name)
            return None

        logger.info(
            "company_lookup_found company_name=%s corp_code=%s corp_name=%s",
            normalized_name,
            row["corp_code"],
            row["corp_name"],
        )
        return CompanyLookupResult(
            corp_code=str(row["corp_code"]).zfill(8),
            corp_name=str(row["corp_name"]),
            company_profile=build_company_profile(row),
        )
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("company_lookup_failed company_name=%s", normalized_name)
        raise RuntimeError("기업 마스터 조회 중 오류가 발생했습니다.") from exc
