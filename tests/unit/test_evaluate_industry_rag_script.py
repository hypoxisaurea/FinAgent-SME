from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

from backend.scripts import evaluate_industry_rag


def test_evaluate_industry_rag_parser_defaults() -> None:
    parser = evaluate_industry_rag.build_parser()
    args = parser.parse_args(["dataset.jsonl"])

    assert args.dataset_path == "dataset.jsonl"
    assert args.output_path == "artifacts/industry_rag_eval/report.json"
    assert args.model is None
    assert args.target == "retriever"


def test_run_evaluation_builds_rows_and_writes_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "case_id": "case-1",
                "user_input": "건설업 평가요소를 설명해줘",
                "reference": "수주잔고와 PF 리스크를 본다.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "report.json"

    monkeypatch.setattr(
        evaluate_industry_rag,
        "build_industry_ragas_eval_rows",
        lambda cases: [
            SimpleNamespace(
                case_id=cases[0].case_id,
                user_input=cases[0].user_input,
                reference=cases[0].reference,
            )
        ],
    )
    monkeypatch.setattr(
        evaluate_industry_rag,
        "run_industry_ragas_evaluation",
        lambda rows, model_name=None, evaluation_target="retriever": _fake_async_report(
            rows,
            model_name,
            evaluation_target,
        ),
    )

    args = evaluate_industry_rag.build_parser().parse_args(
        [str(dataset_path), "--output-path", str(output_path), "--model", "gpt-4o-mini"]
    )
    report = evaluate_industry_rag.run_evaluation(args)

    assert report["case_count"] == 1
    assert report["model_name"] == "gpt-4o-mini"
    assert report["evaluation_target"] == "retriever"
    stored = json.loads(output_path.read_text(encoding="utf-8"))
    assert stored["case_count"] == 1


def test_run_evaluation_supports_agent_target(monkeypatch, tmp_path: Path) -> None:
    dataset_path = tmp_path / "agent-dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "case_id": "agent-case-1",
                "user_input": "건설업 업황과 평가요소를 설명해줘",
                "reference": "건설업은 수주잔고와 PF 리스크를 중심으로 평가한다.",
                "company_name": "테스트기업",
                "corp_code": "00123456",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        evaluate_industry_rag,
        "build_industry_agent_ragas_eval_rows",
        lambda cases: _fake_async_rows(cases),
    )
    monkeypatch.setattr(
        evaluate_industry_rag,
        "run_industry_ragas_evaluation",
        lambda rows, model_name=None, evaluation_target="retriever": _fake_async_report(
            rows,
            model_name,
            evaluation_target,
        ),
    )

    args = evaluate_industry_rag.build_parser().parse_args(
        [str(dataset_path), "--target", "agent"]
    )
    report = evaluate_industry_rag.run_evaluation(args)

    assert report["evaluation_target"] == "agent"
    assert report["case_count"] == 1


async def _fake_async_report(rows, model_name, evaluation_target):
    return {
        "evaluation_target": evaluation_target,
        "model_name": model_name,
        "case_count": len(rows),
        "unavailable_case_count": 0,
        "summary": {},
        "cases": [],
    }


async def _fake_async_rows(cases):
    return [
        SimpleNamespace(
            case_id=cases[0].case_id,
            user_input=cases[0].user_input,
            reference=cases[0].reference,
        )
    ]
