from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from backend.common.logging import configure_logging
from backend.scripts.evaluate_industry_rag import run_evaluation

logger = logging.getLogger(__name__)
DEFAULT_ARTIFACT_DIR = Path("backend/rag/artifacts/industry_rag_eval")
EVALUATION_TARGETS = (
    (
        "retriever",
        Path("backend/rag/eval_datasets/industry_methodology.jsonl"),
        "report.json",
    ),
    (
        "agent",
        Path("backend/rag/eval_datasets/industry_agent.jsonl"),
        "agent_report.json",
    ),
)


def regenerate_artifacts(
    *,
    artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR,
    model: str | None = None,
) -> list[Path]:
    """고정 평가셋으로 retriever/agent RAGAS artifact를 모두 재생성한다."""
    target_dir = Path(artifact_dir)
    generated_paths: list[Path] = []
    for target, dataset_path, filename in EVALUATION_TARGETS:
        output_path = target_dir / filename
        run_evaluation(
            argparse.Namespace(
                dataset_path=str(dataset_path),
                output_path=str(output_path),
                model=model,
                target=target,
            )
        )
        generated_paths.append(output_path)
        logger.info(
            "industry_ragas_artifact_regenerated target=%s output_path=%s",
            target,
            output_path,
        )
    return generated_paths


def build_parser() -> argparse.ArgumentParser:
    """RAGAS artifact 일괄 재생성 CLI 파서를 생성한다."""
    parser = argparse.ArgumentParser(
        description="고정 평가셋의 RAGAS artifact를 일괄 재생성합니다."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--model", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """RAGAS artifact 일괄 재생성 CLI 진입점."""
    configure_logging()
    args = build_parser().parse_args(argv)
    regenerate_artifacts(artifact_dir=args.artifact_dir, model=args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
