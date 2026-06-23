from __future__ import annotations

import json
from pathlib import Path

from backend.scripts import regenerate_industry_rag_artifacts
from backend.scripts.verify_industry_rag_artifacts import verify_industry_rag_artifacts


def test_committed_rag_artifact_manifest_matches_report_files() -> None:
    manifest_path = Path("backend/rag/artifacts/industry_rag_eval/regeneration_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["artifact_count"] == len(manifest["artifacts"])
    assert {artifact["target"] for artifact in manifest["artifacts"]} == {
        "retriever",
        "agent",
    }
    for artifact in manifest["artifacts"]:
        report = json.loads(Path(artifact["output_path"]).read_text(encoding="utf-8"))
        assert artifact["evaluation_target"] == report["evaluation_target"]
        assert artifact["model_name"] == report["model_name"]
        assert artifact["case_count"] == report["case_count"]
        assert artifact["unavailable_case_count"] == report["unavailable_case_count"]
        assert artifact["summary"] == report["summary"]


def test_committed_rag_artifacts_pass_smoke_verification(tmp_path: Path) -> None:
    evidence = verify_industry_rag_artifacts(output_path=tmp_path / "evidence.json")

    assert evidence["verified"] is True
    assert evidence["artifact_count"] == 2
    assert evidence["targets"] == ["agent", "retriever"]
    assert {artifact["target"] for artifact in evidence["artifacts"]} == {
        "retriever",
        "agent",
    }
    assert all(
        artifact["scored_metric_count"] > 0 for artifact in evidence["artifacts"]
    )


def test_ragas_artifacts_workflow_runs_smoke_verification() -> None:
    import yaml

    workflow = yaml.safe_load(
        Path(".github/workflows/ragas-artifacts.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["ragas-artifacts"]["steps"]

    assert workflow["name"] == "RAGAS Artifacts"
    assert "workflow_dispatch" in workflow[True]
    assert any(
        step.get("run")
        == ".venv/bin/python -m backend.scripts.verify_industry_rag_artifacts"
        for step in steps
    )
    assert any(
        step.get("uses") == "actions/upload-artifact@v4"
        and step.get("with", {}).get("name")
        == "industry-ragas-artifact-verification"
        and step.get("with", {}).get("path")
        == "artifacts/industry_rag_artifact_verification.json"
        for step in steps
    )


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
