from __future__ import annotations

import json
from pathlib import Path

from backend.scripts import regenerate_industry_rag_artifacts


def test_regenerate_artifacts_runs_both_fixed_evaluation_targets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []
    monkeypatch.setattr(
        regenerate_industry_rag_artifacts,
        "run_evaluation",
        lambda args: calls.append(args) or {},
    )

    paths = regenerate_industry_rag_artifacts.regenerate_artifacts(
        artifact_dir=tmp_path,
        model="judge-model",
    )

    assert [call.target for call in calls] == ["retriever", "agent"]
    assert all(call.model == "judge-model" for call in calls)
    assert paths == [tmp_path / "report.json", tmp_path / "agent_report.json"]
    manifest = json.loads(
        (tmp_path / "regeneration_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["artifact_count"] == 2
    assert manifest["model_override"] == "judge-model"
    assert [artifact["target"] for artifact in manifest["artifacts"]] == [
        "retriever",
        "agent",
    ]


def test_regenerate_artifacts_can_limit_targets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = []
    monkeypatch.setattr(
        regenerate_industry_rag_artifacts,
        "run_evaluation",
        lambda args: calls.append(args)
        or {
            "evaluation_target": args.target,
            "model_name": args.model,
            "case_count": 1,
            "unavailable_case_count": 0,
            "summary": {},
        },
    )

    paths = regenerate_industry_rag_artifacts.regenerate_artifacts(
        artifact_dir=tmp_path,
        targets=("retriever",),
    )

    assert [call.target for call in calls] == ["retriever"]
    assert paths == [tmp_path / "report.json"]
    manifest = json.loads(
        (tmp_path / "regeneration_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["artifact_count"] == 1
    assert manifest["artifacts"][0]["target"] == "retriever"
