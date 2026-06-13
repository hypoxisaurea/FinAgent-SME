from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import backend.tools.company_registry as company_registry_tools
import pandas as pd
from backend.data.repositories.company_registry import (
    add_created_at_column,
    save_outputs_to_database,
)

logger = logging.getLogger(__name__)


class _PipelineArgs:
    api_key: str | None = None
    env_file: str | None = None


def execute_dart_pipeline(
    year: int,
    sample_size: int | None = None,
    skip_db_save: bool = False,
) -> dict[str, Any]:
    """DART 기반 기업 마스터/재무 피처 구축 use-case를 실행한다."""
    if company_registry_tools.dart is None:
        raise ModuleNotFoundError("dart_fss가 설치되어 있지 않습니다.")

    api_key = company_registry_tools.resolve_api_key(_PipelineArgs())
    company_registry_tools.dart.set_api_key(api_key=api_key)

    _, sme_df = company_registry_tools.load_sme_candidates(sample_size=sample_size)

    (
        processed_records,
        statement_records,
        error_logs,
        stats,
    ) = company_registry_tools.run_collection(
        sme_df=sme_df,
        business_year=year,
        report_code=company_registry_tools.DEFAULT_REPORT_CODE,
    )

    created_at = datetime.now().strftime("%Y-%m-%d")
    final_df = company_registry_tools.build_final_dataframe(processed_records)
    final_df = add_created_at_column(final_df, created_at)
    statement_detail_df = company_registry_tools.build_statement_detail_dataframe(
        statement_records
    )
    statement_detail_df = add_created_at_column(statement_detail_df, created_at)
    sme_list_df = company_registry_tools.build_sme_list_dataframe(final_df)
    company_profile_df, profile_errors, profile_stats = (
        company_registry_tools.build_company_profile_dataframe(sme_list_df)
    )
    company_profile_df = add_created_at_column(company_profile_df, created_at)
    error_df = pd.DataFrame(error_logs)
    if profile_errors:
        error_df = pd.concat(
            [error_df, pd.DataFrame(profile_errors)],
            ignore_index=True,
        )

    db_save_counts: dict[str, int] = {}
    if not skip_db_save:
        db_save_counts = save_outputs_to_database(
            sme_list_df,
            company_profile_df,
            final_df,
            statement_detail_df,
            error_df,
        )

    result = {
        "status": "success",
        "stats": stats,
        "sme_count": len(sme_list_df),
        "financial_data_count": len(final_df),
        "financial_statement_detail_count": len(statement_detail_df),
        "company_profile_count": len(company_profile_df),
        "db_save_counts": db_save_counts,
        "source": "dart",
    }
    result["stats"].update(profile_stats)
    logger.info(
        (
            "company_registry_pipeline_finished year=%s sample_size=%s "
            "skip_db_save=%s sme_count=%s financial_data_count=%s "
            "statement_detail_count=%s"
        ),
        year,
        sample_size,
        skip_db_save,
        result["sme_count"],
        result["financial_data_count"],
        result["financial_statement_detail_count"],
    )
    return result
