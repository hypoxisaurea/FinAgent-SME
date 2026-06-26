from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from backend.common.logging import configure_logging
from backend.scripts.evaluate_industry_rag import run_evaluation

logger = logging.getLogger(__name__)
DEFAULT_ARTIFACT_DIR = Path("backend/rag/artifacts/industry_rag_eval")
DEFAULT_MANIFEST_NAME = "regeneration_manifest.json"
EvaluationTarget = Literal["retriever", "agent"]
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
    manifest_path: str | Path | None = None,
    model: str | None = None,
    targets: Sequence[EvaluationTarget] = ("retriever", "agent"),
) -> list[Path]:
    """고정 평가셋으로 retriever/agent RAGAS artifact를 모두 재생성한다."""
    target_dir = Path(artifact_dir)
    generated_paths: list[Path] = []
    manifest_entries: list[dict[str, object]] = []
    for target, dataset_path, filename in EVALUATION_TARGETS:
        if target not in targets:
            continue
        output_path = target_dir / filename
        report = run_evaluation(
            argparse.Namespace(
                dataset_path=str(dataset_path),
                output_path=str(output_path),
                model=model,
                target=target,
            )
        )
        generated_paths.append(output_path)
        manifest_entries.append(
            {
                "target": target,
                "dataset_path": str(dataset_path),
                "output_path": str(output_path),
                "evaluation_target": report.get("evaluation_target"),
                "model_name": report.get("model_name"),
                "case_count": report.get("case_count"),
                "unavailable_case_count": report.get("unavailable_case_count"),
                "summary": report.get("summary", {}),
            }
        )
        logger.info(
            "industry_ragas_artifact_regenerated target=%s output_path=%s",
            target,
            output_path,
        )
    _write_regeneration_manifest(
        manifest_path=Path(manifest_path) if manifest_path else target_dir / DEFAULT_MANIFEST_NAME,
        artifact_dir=target_dir,
        model=model,
        artifacts=manifest_entries,
    )
    return generated_paths


def build_parser() -> argparse.ArgumentParser:
    """RAGAS artifact 일괄 재생성 CLI 파서를 생성한다."""
    parser = argparse.ArgumentParser(
        description="고정 평가셋의 RAGAS artifact를 일괄 재생성합니다."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument(
        "--manifest-path",
        default=None,
        help=(
            "재생성 실행 요약 JSON 경로. 기본값은 "
            f"<artifact-dir>/{DEFAULT_MANIFEST_NAME}"
        ),
    )
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--targets",
        choices=("retriever", "agent"),
        default=("retriever", "agent"),
        nargs="+",
        help="재생성할 평가 target. 기본값은 retriever agent 모두 실행.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """RAGAS artifact 일괄 재생성 CLI 진입점."""
    configure_logging()
    args = build_parser().parse_args(argv)
    regenerate_artifacts(
        artifact_dir=args.artifact_dir,
        manifest_path=args.manifest_path,
        model=args.model,
        targets=args.targets,
    )
    return 0


def _write_regeneration_manifest(
    *,
    manifest_path: Path,
    artifact_dir: Path,
    model: str | None,
    artifacts: list[dict[str, object]],
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "regenerated_at": datetime.now(UTC).isoformat(),
        "artifact_dir": str(artifact_dir),
        "model_override": model,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    logger.info(
        "industry_ragas_artifact_manifest_written manifest_path=%s artifact_count=%s",
        manifest_path,
        len(artifacts),
    )


if __name__ == "__main__":
    raise SystemExit(main())
