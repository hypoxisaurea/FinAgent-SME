from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DEFAULT_ARTIFACT_DIR = Path("backend/rag/artifacts/industry_rag_eval")
DEFAULT_MANIFEST_PATH = DEFAULT_ARTIFACT_DIR / "regeneration_manifest.json"
DEFAULT_OUTPUT_PATH = Path("artifacts/industry_rag_artifact_verification.json")
EXPECTED_TARGETS = frozenset({"retriever", "agent"})


def verify_industry_rag_artifacts(
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """커밋된 retriever/agent RAGAS artifact와 manifest 정합성을 검증한다."""
    manifest_file = Path(manifest_path)
    manifest = _read_json_object(manifest_file)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("regeneration_manifest.json의 artifacts는 배열이어야 합니다.")
    if manifest.get("artifact_count") != len(artifacts):
        raise ValueError("artifact_count가 artifacts 개수와 일치하지 않습니다.")

    targets = {
        str(artifact.get("target"))
        for artifact in artifacts
        if isinstance(artifact, dict)
    }
    if targets != EXPECTED_TARGETS:
        raise ValueError(
            "RAGAS artifact target이 retriever/agent와 일치하지 않습니다: "
            f"{sorted(targets)}"
        )

    evidence_artifacts: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("manifest artifact 항목은 객체여야 합니다.")
        evidence_artifacts.append(_verify_manifest_artifact(artifact))

    evidence = {
        "verified": True,
        "verified_at": datetime.now(UTC).isoformat(),
        "manifest_path": str(manifest_file),
        "artifact_count": len(evidence_artifacts),
        "targets": sorted(targets),
        "artifacts": evidence_artifacts,
    }
    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "industry_ragas_artifacts_verified manifest_path=%s output_path=%s",
        manifest_file,
        target_path,
    )
    return evidence


def build_parser() -> argparse.ArgumentParser:
    """RAGAS artifact smoke 검증 CLI 파서를 생성한다."""
    parser = argparse.ArgumentParser(
        description="커밋된 Industry RAGAS artifact와 manifest 정합성을 검증합니다."
    )
    parser.add_argument("--manifest-path", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """RAGAS artifact smoke 검증 CLI 진입점."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    args = build_parser().parse_args(argv)
    verify_industry_rag_artifacts(
        manifest_path=args.manifest_path,
        output_path=args.output_path,
    )
    return 0


def _verify_manifest_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    output_path = _require_string(artifact, "output_path")
    dataset_path = _require_string(artifact, "dataset_path")
    report = _read_json_object(Path(output_path))

    for key in (
        "evaluation_target",
        "model_name",
        "case_count",
        "unavailable_case_count",
        "summary",
    ):
        if artifact.get(key) != report.get(key):
            raise ValueError(f"{output_path}의 {key}가 manifest와 일치하지 않습니다.")

    case_count = _require_int(report, "case_count")
    scored_metric_count = _require_int(report, "scored_metric_count")
    if case_count <= 0:
        raise ValueError(f"{output_path}의 case_count가 1 이상이어야 합니다.")
    if scored_metric_count <= 0:
        raise ValueError(f"{output_path}의 scored_metric_count가 1 이상이어야 합니다.")
    if not Path(dataset_path).exists():
        raise ValueError(f"dataset_path가 존재하지 않습니다: {dataset_path}")

    summary = report.get("summary")
    if not isinstance(summary, dict) or not summary:
        raise ValueError(f"{output_path}의 summary가 비어 있습니다.")

    metric_names = []
    for metric_name, metric_summary in summary.items():
        if not isinstance(metric_summary, dict):
            raise ValueError(f"{output_path}의 {metric_name} summary가 객체가 아닙니다.")
        scored_cases = _require_int(metric_summary, "scored_cases")
        mean = metric_summary.get("mean")
        if scored_cases <= 0:
            raise ValueError(f"{output_path}의 {metric_name} scored_cases가 0입니다.")
        if not isinstance(mean, (int, float)):
            raise ValueError(f"{output_path}의 {metric_name} mean이 숫자가 아닙니다.")
        metric_names.append(str(metric_name))

    return {
        "target": artifact.get("target"),
        "dataset_path": dataset_path,
        "output_path": output_path,
        "evaluation_target": report.get("evaluation_target"),
        "case_count": case_count,
        "scored_metric_count": scored_metric_count,
        "metrics": sorted(metric_names),
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 파일은 객체여야 합니다: {path}")
    return payload


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}는 비어 있지 않은 문자열이어야 합니다.")
    return value


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key}는 정수여야 합니다.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
