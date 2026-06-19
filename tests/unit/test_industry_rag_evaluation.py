from __future__ import annotations

import asyncio
import builtins
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from backend.rag import evaluation


def test_repo_sample_datasets_use_index_metadata_values() -> None:
    retriever_cases = evaluation.load_industry_ragas_eval_cases(
        "backend/rag/eval_datasets/industry_methodology.sample.jsonl"
    )
    agent_cases = evaluation.load_industry_agent_ragas_eval_cases(
        "backend/rag/eval_datasets/industry_agent.sample.jsonl"
    )

    assert len(retriever_cases) == 8
    assert len(agent_cases) == 8
    assert {case.sub_sector for case in retriever_cases} == {
        "건설",
        "반도체",
        "조선",
        "정유",
        "자동차",
        "철강",
        "의류",
        "항공운송",
    }
    assert {case.sub_sector for case in agent_cases} == {
        case.sub_sector for case in retriever_cases
    }


def test_load_industry_ragas_eval_cases_reads_jsonl(tmp_path: Path) -> None:
    dataset_path = tmp_path / "industry_eval.jsonl"
    dataset_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "case-1",
                        "user_input": "건설업 평가요소를 설명해줘",
                        "reference": "수주잔고와 PF 리스크를 본다.",
                        "ksic_code": "F 건설업",
                    },
                    ensure_ascii=False,
                ),
                "",
                json.dumps(
                    {
                        "case_id": "case-2",
                        "user_input": "반도체업 핵심 요인을 설명해줘",
                        "reference": "시장지위와 CAPEX 부담을 본다.",
                        "ksic_code": "C 제조업",
                        "sub_sector": "반도체",
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    cases = evaluation.load_industry_ragas_eval_cases(dataset_path)

    assert [case.case_id for case in cases] == ["case-1", "case-2"]
    assert cases[0].top_k == evaluation.DEFAULT_TOP_K
    assert cases[1].sub_sector == "반도체"


def test_build_industry_ragas_eval_rows_maps_retriever_payload() -> None:
    cases = [
        evaluation.IndustryRagasEvalCase(
            case_id="case-1",
            user_input="건설업 평가요소를 설명해줘",
            reference="수주잔고와 PF 리스크를 본다.",
            industry_name="건설업",
            ksic_code="F 건설업",
            top_k=3,
        )
    ]
    captured: dict[str, Any] = {}

    def fake_retriever(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "industry_methodology": {
                "summary": "건설업은 수주잔고와 PF 우발채무가 핵심 리스크다.",
                "unavailable": False,
                "error": None,
            },
            "methodology_sources": [{"filename": "construction.pdf", "page": 7}],
            "retrieved_contexts": ["건설업은 수주잔고와 PF 우발채무가 핵심 리스크다."],
        }

    rows = evaluation.build_industry_ragas_eval_rows(
        cases,
        retriever=fake_retriever,
    )

    assert captured == {
        "query": "건설업 평가요소를 설명해줘",
        "industry_name": "건설업",
        "ksic_code": "F 건설업",
        "sub_sector": None,
        "top_k": 3,
        "include_contexts": True,
    }
    assert rows[0].response == "건설업은 수주잔고와 PF 우발채무가 핵심 리스크다."
    assert rows[0].retrieved_contexts == [
        "건설업은 수주잔고와 PF 우발채무가 핵심 리스크다."
    ]
    assert rows[0].methodology_sources == [{"filename": "construction.pdf", "page": 7}]


def test_load_industry_agent_ragas_eval_cases_reads_jsonl(tmp_path: Path) -> None:
    dataset_path = tmp_path / "industry_agent_eval.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "case_id": "agent-case-1",
                "user_input": "건설업 업황과 평가요소를 설명해줘",
                "reference": "건설업은 수주잔고와 PF 리스크를 중심으로 평가한다.",
                "company_name": "테스트기업",
                "corp_code": "00123456",
                "ksic_code": "F 건설업",
                "financial_ratios": {"debt_ratio": 1.2},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cases = evaluation.load_industry_agent_ragas_eval_cases(dataset_path)

    assert len(cases) == 1
    assert cases[0].corp_code == "00123456"
    assert cases[0].ksic_code == "F 건설업"
    assert cases[0].financial_ratios == {"debt_ratio": 1.2}


def test_load_jsonl_cases_missing_file_guides_sample_paths(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.jsonl"

    try:
        evaluation.load_industry_agent_ragas_eval_cases(missing_path)
    except FileNotFoundError as exc:
        assert "industry_agent.sample.jsonl" in str(exc)
        assert "industry_methodology.sample.jsonl" in str(exc)
    else:
        raise AssertionError("FileNotFoundError was not raised")


def test_load_jsonl_cases_resolves_repo_relative_path(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    dataset_path = repo_root / "backend" / "rag" / "eval_datasets" / "sample.jsonl"
    dataset_path.parent.mkdir(parents=True)
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
    monkeypatch.setattr(
        evaluation,
        "PROJECT_ROOT",
        repo_root,
    )

    cases = evaluation.load_industry_ragas_eval_cases(
        "backend/rag/eval_datasets/sample.jsonl"
    )

    assert len(cases) == 1
    assert cases[0].case_id == "case-1"


def test_build_industry_agent_response_text_combines_rag_and_agent_fields() -> None:
    response = evaluation.build_industry_agent_response_text(
        {
            "ksic_code": "F 건설업",
            "industry_summary": {"sector_note": "PF 익스포저와 수주 변동성이 큰 업종입니다."},
            "industry_outlook": {
                "outlook_score": "Medium",
                "industry_methodology": {
                    "summary": "건설업은 수주잔고와 PF 우발채무를 핵심적으로 본다.",
                    "key_risk_factors": [
                        "PF 우발채무 부담이 확대될 수 있다.",
                        "수주잔고 감소 시 실적 변동성이 확대된다.",
                    ],
                },
            },
            "business_cycle": {"phase": "둔화"},
            "macro_indicators": {"note": "금리 부담이 업황에 부정적이다."},
        }
    )

    assert "업종 분류는 F 건설업입니다." in response
    assert "현재 업황 평가는 Medium입니다." in response
    assert "신용평가방법론 요약은 건설업은 수주잔고와 PF 우발채무를 핵심적으로 본다." in response
    assert "경기 국면은 둔화 단계입니다." in response


def test_build_industry_agent_ragas_eval_rows_maps_agent_output() -> None:
    class FakeIndustryAgent:
        async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
            assert payload["corp_code"] == "00123456"
            return {
                "ksic_code": "F 건설업",
                "industry_summary": {
                    "sector_note": "PF 익스포저와 수주 변동성이 큰 업종입니다."
                },
                "industry_outlook": {
                    "outlook_score": "Medium",
                    "industry_methodology": {
                        "industry_name": "건설업",
                        "summary": "건설업은 수주잔고와 PF 우발채무를 본다.",
                        "unavailable": False,
                        "error": None,
                    },
                    "methodology_sources": [
                        {
                            "filename": "construction.pdf",
                            "page": 7,
                            "sub_sector": "건설",
                        }
                    ],
                },
                "business_cycle": {"phase": "둔화"},
                "macro_indicators": {"note": "금리 부담이 업황에 부정적이다."},
                "industry_tool_errors": [],
                "status": "success",
                "error_code": "OK",
                "fallback_used": False,
                "latency_ms": 12,
                "agent_execution": {
                    "status": "success",
                    "error_code": "OK",
                    "fallback_used": False,
                    "latency_ms": 12,
                },
            }

    captured: dict[str, Any] = {}

    def fake_retriever(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "retrieved_contexts": [
                "건설업은 수주잔고와 PF 우발채무를 핵심적으로 본다."
            ]
        }

    rows = asyncio.run(
        evaluation.build_industry_agent_ragas_eval_rows(
            [
                evaluation.IndustryAgentRagasEvalCase(
                    case_id="agent-case-1",
                    user_input="건설업 업황과 평가요소를 설명해줘",
                    reference="건설업은 수주잔고와 PF 리스크를 중심으로 평가한다.",
                    company_name="테스트기업",
                    corp_code="00123456",
                    ksic_code="F 건설업",
                    sub_sector="건설",
                )
            ],
            agent=FakeIndustryAgent(),
            retriever=fake_retriever,
        )
    )

    assert captured == {
        "query": "건설업 업황과 평가요소를 설명해줘",
        "ksic_code": "F 건설업",
        "sub_sector": "건설",
        "include_contexts": True,
    }
    assert rows[0].industry_name == "건설업"
    assert rows[0].response
    assert rows[0].retrieved_contexts == [
        "건설업은 수주잔고와 PF 우발채무를 핵심적으로 본다."
    ]


def test_offline_industry_eval_provider_uses_case_ksic_and_retriever() -> None:
    captured: dict[str, Any] = {}

    def fake_retriever(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "industry_methodology": {
                "summary": "건설업은 수주잔고와 PF 우발채무를 본다.",
                "unavailable": False,
                "error": None,
            },
            "methodology_sources": [{"filename": "construction.pdf", "page": 7}],
            "retrieved_contexts": ["건설업은 수주잔고와 PF 우발채무를 본다."],
        }

    provider = evaluation._OfflineIndustryEvalProvider(
        evaluation.IndustryAgentRagasEvalCase(
            case_id="agent-case-1",
            user_input="건설업 업황과 평가요소를 설명해줘",
            reference="ref",
            company_name="테스트기업",
            corp_code="00123456",
            ksic_code="F 건설업",
            sub_sector="건설",
        ),
        retriever=fake_retriever,
    )

    mapped = provider.map_corp_to_ksic("00123456")
    outlook = provider.get_industry_outlook("F 건설업")

    assert mapped["ksic_code"] == "F 건설업"
    assert captured["ksic_code"] == "F 건설업"
    assert captured["sub_sector"] == "건설"
    assert outlook["industry_methodology"]["summary"] == "건설업은 수주잔고와 PF 우발채무를 본다."


def test_summarize_case_results_ignores_skipped_metrics() -> None:
    case_results = [
        evaluation.IndustryRagasCaseResult(
            case_id="case-1",
            user_input="q1",
            response="r1",
            reference="ref1",
            metric_scores={
                "context_precision": evaluation.IndustryRagasMetricScore(value=0.8),
                "context_recall": evaluation.IndustryRagasMetricScore(skipped="no context"),
                "faithfulness": evaluation.IndustryRagasMetricScore(value=0.6),
                "response_groundedness": evaluation.IndustryRagasMetricScore(value=0.7),
                "factual_correctness": evaluation.IndustryRagasMetricScore(value=0.9),
            },
        ),
        evaluation.IndustryRagasCaseResult(
            case_id="case-2",
            user_input="q2",
            response="r2",
            reference="ref2",
            metric_scores={
                "context_precision": evaluation.IndustryRagasMetricScore(value=0.4),
                "context_recall": evaluation.IndustryRagasMetricScore(value=0.5),
                "faithfulness": evaluation.IndustryRagasMetricScore(value=0.2),
                "response_groundedness": evaluation.IndustryRagasMetricScore(skipped="no response"),
                "factual_correctness": evaluation.IndustryRagasMetricScore(value=0.3),
            },
        ),
    ]

    summary = evaluation._summarize_case_results(case_results)

    assert summary["context_precision"] == {
        "mean": 0.6,
        "scored_cases": 2,
        "skipped_cases": 0,
    }
    assert summary["context_recall"] == {
        "mean": 0.5,
        "scored_cases": 1,
        "skipped_cases": 1,
    }
    assert summary["response_groundedness"] == {
        "mean": 0.7,
        "scored_cases": 1,
        "skipped_cases": 1,
    }
    assert evaluation._summarize_metric_coverage(summary) == {
        "status": "partial",
        "scored_metric_count": 8,
        "skipped_metric_count": 2,
    }


def test_summarize_metric_coverage_marks_complete_report() -> None:
    coverage = evaluation._summarize_metric_coverage(
        {
            "context_precision": {"scored_cases": 2, "skipped_cases": 0},
            "context_recall": {"scored_cases": 2, "skipped_cases": 0},
        }
    )

    assert coverage == {
        "status": "complete",
        "scored_metric_count": 4,
        "skipped_metric_count": 0,
    }


def test_load_ragas_runtime_error_guides_installation(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("ragas"):
            raise ImportError("ragas missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    try:
        evaluation._load_ragas_runtime()
    except RuntimeError as exc:
        assert "RAGAS import에 실패했습니다." in str(exc)
    else:
        raise AssertionError("RuntimeError was not raised")


def test_ensure_ragas_langchain_compatibility_registers_shim(monkeypatch) -> None:
    sys.modules.pop("langchain_community.chat_models.vertexai", None)

    original_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> Any:
        if name == "langchain_community.chat_models.vertexai":
            raise ModuleNotFoundError(name)
        return original_import_module(name, package)

    monkeypatch.setattr(evaluation.importlib, "import_module", fake_import_module)

    try:
        evaluation._ensure_ragas_langchain_compatibility()
        shim_module = sys.modules["langchain_community.chat_models.vertexai"]
        assert hasattr(shim_module, "ChatVertexAI")
    finally:
        sys.modules.pop("langchain_community.chat_models.vertexai", None)


def test_evaluate_row_with_ragas_skips_missing_contexts() -> None:
    class FakeMetric:
        async def ascore(self, **_: Any) -> Any:
            raise AssertionError("should not be called")

    row = evaluation.IndustryRagasEvalRow(
        case_id="case-1",
        user_input="건설업 평가요소를 설명해줘",
        reference="수주잔고와 PF 리스크를 본다.",
        response="",
        retrieved_contexts=[],
    )

    result = asyncio.run(
        evaluation._evaluate_row_with_ragas(
            row=row,
            metrics={
                "context_precision": FakeMetric(),
                "context_recall": FakeMetric(),
                "faithfulness": FakeMetric(),
                "response_groundedness": FakeMetric(),
                "factual_correctness": FakeMetric(),
            },
        )
    )

    assert (
        result.metric_scores["context_precision"].skipped
        == "retrieved_contexts 비어 있음"
    )
    assert result.metric_scores["faithfulness"].skipped == "retrieved_contexts 비어 있음"
    assert result.metric_scores["factual_correctness"].skipped == "response 비어 있음"


def test_evaluate_row_with_ragas_only_scores_supplied_target_metrics() -> None:
    class FakeMetric:
        async def ascore(self, **_: Any) -> Any:
            return SimpleNamespace(value=0.9, reason=None)

    row = evaluation.IndustryRagasEvalRow(
        case_id="case-1",
        user_input="건설업 평가요소를 설명해줘",
        reference="수주잔고와 PF 리스크를 본다.",
        response="건설업 평가 요약",
        retrieved_contexts=["건설업은 수주잔고와 PF 리스크를 평가한다."],
    )

    result = asyncio.run(
        evaluation._evaluate_row_with_ragas(
            row=row,
            metrics={
                "context_precision": FakeMetric(),
                "context_recall": FakeMetric(),
            },
        )
    )

    assert set(result.metric_scores) == {"context_precision", "context_recall"}


def test_run_metric_normalizes_value_and_reason() -> None:
    async def fake_coroutine() -> Any:
        return SimpleNamespace(value=0.81234, reason="  grounded  ")

    score = asyncio.run(
        evaluation._run_metric(
            "faithfulness",
            fake_coroutine(),
            "case-1",
        )
    )

    assert score.value == 0.8123
    assert score.reason == "grounded"


def test_run_metric_skips_non_finite_value() -> None:
    async def fake_coroutine() -> Any:
        return SimpleNamespace(value=float("nan"), reason=None)

    score = asyncio.run(
        evaluation._run_metric(
            "response_groundedness",
            fake_coroutine(),
            "case-1",
        )
    )

    assert score.value is None
    assert score.skipped == "metric이 유효한 숫자 점수를 반환하지 않음"


def test_ensure_any_metric_succeeded_raises_when_all_metrics_skipped() -> None:
    case_results = [
        evaluation.IndustryRagasCaseResult(
            case_id="case-1",
            user_input="q1",
            response="r1",
            reference="ref1",
            metric_scores={
                "faithfulness": evaluation.IndustryRagasMetricScore(
                    skipped="Connection error."
                )
            },
        )
    ]

    try:
        evaluation._ensure_any_metric_succeeded(case_results)
    except RuntimeError as exc:
        assert "점수를 하나도 생성하지 못했습니다" in str(exc)
        assert "Connection error." in str(exc)
    else:
        raise AssertionError("RuntimeError was not raised")


def test_validate_rag_eval_rows_raises_when_all_contexts_missing() -> None:
    rows = [
        evaluation.IndustryRagasEvalRow(
            case_id="case-1",
            user_input="q1",
            reference="ref1",
            response="resp1",
            retrieved_contexts=[],
            unavailable=True,
            error="chromadb is required for industry RAG",
        ),
        evaluation.IndustryRagasEvalRow(
            case_id="case-2",
            user_input="q2",
            reference="ref2",
            response="resp2",
            retrieved_contexts=[],
            unavailable=True,
            error="chromadb is required for industry RAG",
        ),
    ]

    try:
        evaluation._validate_rag_eval_rows(rows, evaluation_target="agent")
    except RuntimeError as exc:
        assert "retrieved_contexts를 하나도 확보하지 못했습니다" in str(exc)
        assert "chromadb is required for industry RAG" in str(exc)
    else:
        raise AssertionError("RuntimeError was not raised")


def test_validate_rag_eval_rows_allows_partial_contexts() -> None:
    rows = [
        evaluation.IndustryRagasEvalRow(
            case_id="case-1",
            user_input="q1",
            reference="ref1",
            response="resp1",
            retrieved_contexts=["ctx"],
        ),
        evaluation.IndustryRagasEvalRow(
            case_id="case-2",
            user_input="q2",
            reference="ref2",
            response="resp2",
            retrieved_contexts=[],
            unavailable=True,
            error="some error",
        ),
    ]

    evaluation._validate_rag_eval_rows(rows, evaluation_target="retriever")
