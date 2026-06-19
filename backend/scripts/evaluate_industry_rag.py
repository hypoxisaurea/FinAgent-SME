from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence

from backend.common.logging import configure_logging
from backend.rag.evaluation import (
    build_industry_agent_ragas_eval_rows,
    build_industry_ragas_eval_rows,
    load_industry_agent_ragas_eval_cases,
    load_industry_ragas_eval_cases,
    run_industry_ragas_evaluation,
    write_industry_ragas_report,
)

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """업종 방법론 RAGAS 평가용 커맨드라인 파서를 생성한다."""
    parser = argparse.ArgumentParser(
        description="업종 신용평가방법론 RAG를 RAGAS로 오프라인 평가합니다.",
    )
    parser.add_argument(
        "dataset_path",
        help="JSONL 평가셋 경로",
    )
    parser.add_argument(
        "--output-path",
        default="artifacts/industry_rag_eval/report.json",
        help="평가 리포트 JSON 저장 경로",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="RAGAS evaluator model override",
    )
    parser.add_argument(
        "--target",
        choices=("retriever", "agent"),
        default="retriever",
        help="평가 대상: retriever 또는 IndustryAnalystAgent",
    )
    return parser


def run_evaluation(args: argparse.Namespace) -> dict[str, object]:
    """평가셋 로드부터 RAGAS 실행, 리포트 저장까지 수행한다."""
    logger.info(
        "industry_ragas_cli_started target=%s dataset_path=%s output_path=%s model_override=%s",
        args.target,
        args.dataset_path,
        args.output_path,
        args.model,
    )
    if args.target == "agent":
        cases = load_industry_agent_ragas_eval_cases(args.dataset_path)
        logger.info(
            "industry_ragas_cases_loaded target=%s case_count=%s",
            args.target,
            len(cases),
        )
        rows = asyncio.run(build_industry_agent_ragas_eval_rows(cases))
    else:
        cases = load_industry_ragas_eval_cases(args.dataset_path)
        logger.info(
            "industry_ragas_cases_loaded target=%s case_count=%s",
            args.target,
            len(cases),
        )
        rows = build_industry_ragas_eval_rows(cases)
    logger.info(
        "industry_ragas_rows_built target=%s row_count=%s",
        args.target,
        len(rows),
    )
    report = asyncio.run(
        run_industry_ragas_evaluation(
            rows,
            model_name=args.model,
            evaluation_target=args.target,
        )
    )
    write_industry_ragas_report(report, args.output_path)
    logger.info(
        "industry_ragas_report_written output_path=%s case_count=%s",
        args.output_path,
        report["case_count"],
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 엔트리포인트."""
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    run_evaluation(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
