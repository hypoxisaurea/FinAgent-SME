from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from datetime import datetime

import pandas as pd
from backend.data.repositories.company_registry import (
    add_created_at_column,
    save_outputs_to_database,
)
from backend.tools import company_registry as company_registry_tools

logger = logging.getLogger(__name__)


class _PipelineArgs:
    api_key: str | None = None
    env_file: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="단일 기업의 DART 재무/상세재무 데이터를 다시 적재합니다.",
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--company-name",
        type=str,
        help="재적재할 기업명",
    )
    target_group.add_argument(
        "--corp-code",
        type=str,
        help="재적재할 8자리 corp_code",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2024,
        help="수집 대상 사업연도",
    )
    parser.add_argument(
        "--report-code",
        type=str,
        default=company_registry_tools.DEFAULT_REPORT_CODE,
        help="DART 보고서 코드",
    )
    parser.add_argument(
        "--skip-db-save",
        action="store_true",
        help="수집만 수행하고 DB 저장은 생략합니다.",
    )
    return parser


def _resolve_target_row(
    *,
    company_name: str | None,
    corp_code: str | None,
) -> pd.Series:
    _, sme_df = company_registry_tools.load_sme_candidates(sample_size=None)

    if corp_code:
        normalized_corp_code = str(corp_code).zfill(8)
        matched_df = sme_df[
            sme_df["corp_code"].astype(str).str.zfill(8) == normalized_corp_code
        ].copy()
    else:
        normalized_company_name = str(company_name or "").strip()
        matched_df = sme_df[
            sme_df["corp_name"].astype(str).str.strip() == normalized_company_name
        ].copy()

    if matched_df.empty:
        target_text = corp_code or company_name
        raise ValueError(f"대상 기업을 찾지 못했습니다: {target_text}")

    return matched_df.iloc[0]


def rebuild_company(args: argparse.Namespace) -> dict[str, object]:
    if company_registry_tools.dart is None:
        raise ModuleNotFoundError("dart_fss가 설치되어 있지 않습니다.")

    api_key = company_registry_tools.resolve_api_key(_PipelineArgs())
    company_registry_tools.dart.set_api_key(api_key=api_key)

    target_row = _resolve_target_row(
        company_name=args.company_name,
        corp_code=args.corp_code,
    )
    corp_code = str(target_row["corp_code"]).zfill(8)
    corp_name = str(target_row["corp_name"]).strip()

    error_logs: list[dict[str, object]] = []
    result = company_registry_tools.process_company(
        target_row,
        args.year,
        args.report_code,
        error_logs,
    )

    status = str(result.get("status"))
    if status != "success":
        raise RuntimeError(
            json.dumps(
                {
                    "corp_code": corp_code,
                    "corp_name": corp_name,
                    "status": status,
                    "errors": error_logs,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    created_at = datetime.now().strftime("%Y-%m-%d")
    processed_records = result.get("records", [])
    statement_records = result.get("statement_records", [])

    final_df = company_registry_tools.build_final_dataframe(processed_records)
    final_df = add_created_at_column(final_df, created_at)
    statement_detail_df = company_registry_tools.build_statement_detail_dataframe(
        statement_records
    )
    statement_detail_df = add_created_at_column(statement_detail_df, created_at)
    sme_list_df = company_registry_tools.build_sme_list_dataframe(final_df)
    company_profile_df, profile_errors, _ = (
        company_registry_tools.build_company_profile_dataframe(sme_list_df)
    )
    company_profile_df = add_created_at_column(company_profile_df, created_at)

    error_df = pd.DataFrame(error_logs + profile_errors)

    db_save_counts: dict[str, int] = {}
    if not args.skip_db_save:
        db_save_counts = save_outputs_to_database(
            sme_list_df=sme_list_df,
            company_profile_df=company_profile_df,
            final_df=final_df,
            statement_detail_df=statement_detail_df,
            error_df=error_df,
        )

    output: dict[str, object] = {
        "status": "success",
        "corp_code": corp_code,
        "corp_name": corp_name,
        "financial_row_count": len(final_df),
        "statement_detail_row_count": len(statement_detail_df),
        "company_profile_row_count": len(company_profile_df),
        "db_save_counts": db_save_counts,
    }
    logger.info(
        "single_company_rebuild_finished corp_code=%s corp_name=%s output=%s",
        corp_code,
        corp_name,
        output,
    )
    return output


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    result = rebuild_company(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
