from __future__ import annotations

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
