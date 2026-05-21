from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agents.company_registry import execute_dart_pipeline

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "ksm_result"


def build_parser() -> argparse.ArgumentParser:
    """DB 구축용 커맨드라인 파서를 생성한다."""
    parser = argparse.ArgumentParser(
        description="DART 기반 기업 마스터/재무 피처 DB를 구축합니다.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2024,
        help="수집 대상 사업연도",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="샘플 기업 수 제한 (빠른 점검용)",
    )
    parser.add_argument(
        "--skip-db-save",
        action="store_true",
        help="CSV만 저장하고 DB 저장은 건너뜁니다.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="CSV 산출물 저장 디렉터리",
    )
    return parser


def run_build_db(args: argparse.Namespace) -> dict[str, Any]:
    """전달된 인자 기준으로 DB 구축 파이프라인을 실행한다."""
    logger.info(
        (
            "build_db_started year=%s sample_size=%s "
            "skip_db_save=%s output_dir=%s"
        ),
        args.year,
        args.sample_size,
        args.skip_db_save,
        args.output_dir,
    )

    result = execute_dart_pipeline(
        year=args.year,
        sample_size=args.sample_size,
        skip_db_save=args.skip_db_save,
        output_dir=args.output_dir,
    )

    logger.info(
        (
            "build_db_finished status=%s sme_count=%s "
            "financial_data_count=%s db_save_counts=%s"
        ),
        result.get("status"),
        result.get("sme_count"),
        result.get("financial_data_count"),
        result.get("db_save_counts"),
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 엔트리포인트."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    run_build_db(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
