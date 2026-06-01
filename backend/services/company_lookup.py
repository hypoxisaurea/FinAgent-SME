from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.agents.company_registry.tools import SME_LIST_TABLE_NAME, create_db_engine
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompanyLookupResult:
    """기업 마스터 조회 결과."""

    corp_code: str
    corp_name: str


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

    engine = create_db_engine()
    try:
        inspector = inspect(engine)
        if not inspector.has_table(SME_LIST_TABLE_NAME):
            raise RuntimeError(
                f"기업 마스터 테이블이 존재하지 않습니다: {SME_LIST_TABLE_NAME}"
            )

        query = text(
            f"""
            SELECT corp_code, corp_name
            FROM {SME_LIST_TABLE_NAME}
            WHERE corp_name = :company_name
            ORDER BY created_at DESC NULLS LAST, corp_code ASC
            LIMIT 1
            """
        )

        with engine.connect() as connection:
            row = (
                connection.execute(
                    query,
                    {"company_name": normalized_name},
                )
                .mappings()
                .first()
            )

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
        )
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("company_lookup_failed company_name=%s", normalized_name)
        raise RuntimeError("기업 마스터 조회 중 오류가 발생했습니다.") from exc
    finally:
        engine.dispose()
