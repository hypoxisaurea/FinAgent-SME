from __future__ import annotations

import importlib
import json
import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import fmean
from types import ModuleType
from typing import Any, Literal, Protocol, TypeVar

from backend.agents.industry_analyst.agent import IndustryAnalystAgent
from backend.common.api_client import build_llm_client_kwargs, get_model_name
from backend.common.contracts import extract_agent_business_output
from backend.common.langfuse import get_async_openai_class
from backend.common.providers import ToolIndustryDataProvider
from backend.rag.retriever import DEFAULT_TOP_K, retrieve_industry_methodology
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

EvaluationTarget = Literal["retriever", "agent"]
RAGAS_METRIC_NAMES = (
    "context_precision",
    "context_recall",
    "faithfulness",
    "response_groundedness",
    "factual_correctness",
)
RAGAS_TARGET_METRICS: dict[EvaluationTarget, tuple[str, ...]] = {
    "retriever": ("context_precision", "context_recall"),
    "agent": RAGAS_METRIC_NAMES,
}
RAGAS_EVALUATOR_MAX_TOKENS = 4096


class IndustryRagasEvalCase(BaseModel):
    """업종 방법론 RAGAS 평가용 단일 케이스."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    user_input: str
    reference: str
    industry_name: str | None = None
    ksic_code: str | None = None
    sub_sector: str | None = None
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=20)
    tags: list[str] = Field(default_factory=list)


class IndustryAgentRagasEvalCase(BaseModel):
    """IndustryAnalystAgent end-to-end 평가용 단일 케이스."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    user_input: str
    reference: str
    company_name: str
    corp_code: str
    ksic_code: str | None = None
    induty_code: str | None = None
    sub_sector: str | None = None
    financial_ratios: dict[str, Any] | None = None
    target_year: int = 2024
    tags: list[str] = Field(default_factory=list)


_EvalCaseT = TypeVar(
    "_EvalCaseT",
    IndustryRagasEvalCase,
    IndustryAgentRagasEvalCase,
)


class IndustryRagasEvalRow(BaseModel):
    """RAG 호출 결과를 RAGAS 입력용으로 정규화한 row."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    user_input: str
    reference: str
    response: str
    retrieved_contexts: list[str] = Field(default_factory=list)
    methodology_sources: list[dict[str, Any]] = Field(default_factory=list)
    industry_name: str | None = None
    ksic_code: str | None = None
    sub_sector: str | None = None
    tags: list[str] = Field(default_factory=list)
    unavailable: bool = False
    error: str | None = None


class IndustryRagasMetricScore(BaseModel):
    """단일 metric 평가 결과."""

    model_config = ConfigDict(extra="forbid")

    value: float | None = None
    reason: str | None = None
    skipped: str | None = None


class IndustryRagasCaseResult(BaseModel):
    """단일 케이스 평가 결과."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    user_input: str
    response: str
    reference: str
    retrieved_contexts: list[str] = Field(default_factory=list)
    methodology_sources: list[dict[str, Any]] = Field(default_factory=list)
    unavailable: bool = False
    error: str | None = None
    metric_scores: dict[str, IndustryRagasMetricScore] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RagasRuntime:
    """RAGAS lazy import bundle."""

    llm_factory: Any
    context_precision_cls: type[Any]
    context_recall_cls: type[Any]
    faithfulness_cls: type[Any]
    factual_correctness_cls: type[Any]
    response_groundedness_cls: type[Any]


class IndustryMethodologyRetriever(Protocol):
    """업종 방법론 검색기 계약."""

    def __call__(
        self,
        *,
        query: str | None = None,
        industry_name: str | None = None,
        ksic_code: str | None = None,
        sub_sector: str | None = None,
        top_k: int = DEFAULT_TOP_K,
        include_contexts: bool = False,
    ) -> dict[str, Any]: ...


class IndustryAgentRunner(Protocol):
    """산업 분석 에이전트 계약."""

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def load_industry_ragas_eval_cases(dataset_path: str | Path) -> list[IndustryRagasEvalCase]:
    """JSONL 평가셋을 읽어 평가 케이스 목록으로 변환한다."""
    return _load_jsonl_cases(dataset_path, IndustryRagasEvalCase)


def load_industry_agent_ragas_eval_cases(
    dataset_path: str | Path,
) -> list[IndustryAgentRagasEvalCase]:
    """IndustryAnalystAgent 평가셋 JSONL을 읽는다."""
    return _load_jsonl_cases(dataset_path, IndustryAgentRagasEvalCase)


def build_industry_ragas_eval_rows(
    cases: list[IndustryRagasEvalCase],
    *,
    retriever: IndustryMethodologyRetriever = retrieve_industry_methodology,
) -> list[IndustryRagasEvalRow]:
    """평가 케이스를 실제 RAG 호출 결과와 결합해 RAGAS 입력 row로 변환한다."""
    logger.info(
        "industry_ragas_row_build_started target=retriever case_count=%s",
        len(cases),
    )
    rows: list[IndustryRagasEvalRow] = []
    for case in cases:
        logger.info(
            "industry_ragas_case_retrieval_started case_id=%s ksic_code=%s sub_sector=%s top_k=%s",
            case.case_id,
            case.ksic_code,
            case.sub_sector,
            case.top_k,
        )
        rag_result = retriever(
            query=case.user_input,
            industry_name=case.industry_name,
            ksic_code=case.ksic_code,
            sub_sector=case.sub_sector,
            top_k=case.top_k,
            include_contexts=True,
        )
        methodology = rag_result.get("industry_methodology", {})
        retrieved_contexts = _string_list(rag_result.get("retrieved_contexts"))
        methodology_sources = _dict_list(rag_result.get("methodology_sources"))
        logger.info(
            "industry_ragas_case_retrieval_finished case_id=%s unavailable=%s retrieved_context_count=%s source_count=%s error=%s",
            case.case_id,
            bool(methodology.get("unavailable", False)),
            len(retrieved_contexts),
            len(methodology_sources),
            _normalize_optional_str(methodology.get("error")),
        )
        rows.append(
            IndustryRagasEvalRow(
                case_id=case.case_id,
                user_input=case.user_input,
                reference=case.reference,
                response=str(methodology.get("summary", "") or ""),
                retrieved_contexts=retrieved_contexts,
                methodology_sources=methodology_sources,
                industry_name=case.industry_name,
                ksic_code=case.ksic_code,
                sub_sector=case.sub_sector,
                tags=list(case.tags),
                unavailable=bool(methodology.get("unavailable", False)),
                error=_normalize_optional_str(methodology.get("error")),
            )
        )
    logger.info(
        "industry_ragas_row_build_finished target=retriever row_count=%s",
        len(rows),
    )
    return rows


async def build_industry_agent_ragas_eval_rows(
    cases: list[IndustryAgentRagasEvalCase],
    *,
    agent: IndustryAgentRunner | None = None,
    retriever: IndustryMethodologyRetriever = retrieve_industry_methodology,
) -> list[IndustryRagasEvalRow]:
    """IndustryAnalystAgent 실행 결과를 RAGAS 입력 row로 변환한다."""
    logger.info(
        "industry_ragas_row_build_started target=agent case_count=%s",
        len(cases),
    )
    rows: list[IndustryRagasEvalRow] = []
    for case in cases:
        logger.info(
            "industry_ragas_agent_case_started case_id=%s company_name=%s corp_code=%s ksic_code=%s sub_sector=%s",
            case.case_id,
            case.company_name,
            case.corp_code,
            case.ksic_code,
            case.sub_sector,
        )
        resolved_agent = agent or IndustryAnalystAgent(
            provider=_OfflineIndustryEvalProvider(case, retriever=retriever)
        )
        payload = {
            "request_id": f"industry-ragas-{case.case_id}",
            "company_name": case.company_name,
            "corp_code": case.corp_code,
            "financial_ratios": case.financial_ratios,
            "target_year": case.target_year,
        }
        agent_result = await resolved_agent.run(payload)
        business_output = extract_agent_business_output(agent_result)
        industry_outlook = _ensure_dict(business_output.get("industry_outlook"))
        methodology = _ensure_dict(industry_outlook.get("industry_methodology"))
        methodology_sources = _dict_list(industry_outlook.get("methodology_sources"))
        retrieved_contexts = _load_agent_retrieved_contexts(
            case=case,
            business_output=business_output,
            methodology_sources=methodology_sources,
            retriever=retriever,
        )
        resolved_error = _resolve_agent_eval_error(
            methodology_error=methodology.get("error"),
            industry_tool_errors=business_output.get("industry_tool_errors"),
        )
        logger.info(
            "industry_ragas_agent_case_finished case_id=%s unavailable=%s retrieved_context_count=%s source_count=%s error=%s",
            case.case_id,
            bool(methodology.get("unavailable", False)),
            len(retrieved_contexts),
            len(methodology_sources),
            resolved_error,
        )
        rows.append(
            IndustryRagasEvalRow(
                case_id=case.case_id,
                user_input=case.user_input,
                reference=case.reference,
                response=build_industry_agent_response_text(business_output),
                retrieved_contexts=retrieved_contexts,
                methodology_sources=methodology_sources,
                industry_name=_normalize_optional_str(methodology.get("industry_name")),
                ksic_code=_normalize_optional_str(business_output.get("ksic_code")),
                sub_sector=_infer_sub_sector_from_sources(methodology_sources),
                tags=list(case.tags),
                unavailable=bool(methodology.get("unavailable", False)),
                error=resolved_error,
            )
        )
    logger.info(
        "industry_ragas_row_build_finished target=agent row_count=%s",
        len(rows),
    )
    return rows


async def run_industry_ragas_evaluation(
    rows: list[IndustryRagasEvalRow],
    *,
    model_name: str | None = None,
    evaluation_target: EvaluationTarget = "retriever",
) -> dict[str, Any]:
    """RAGAS로 업종 방법론 RAG 품질을 평가하고 요약 리포트를 반환한다."""
    _validate_rag_eval_rows(rows, evaluation_target=evaluation_target)
    runtime = _load_ragas_runtime()
    client_class = get_async_openai_class()
    client = client_class(
        **build_llm_client_kwargs(timeout=60),
        max_retries=0,
    )
    resolved_model_name = model_name or get_model_name()
    llm = runtime.llm_factory(
        resolved_model_name,
        provider="openai",
        client=client,
        max_tokens=RAGAS_EVALUATOR_MAX_TOKENS,
    )
    available_metrics = {
        "context_precision": runtime.context_precision_cls(llm=llm),
        "context_recall": runtime.context_recall_cls(llm=llm),
        "faithfulness": runtime.faithfulness_cls(llm=llm),
        "response_groundedness": runtime.response_groundedness_cls(llm=llm),
        "factual_correctness": runtime.factual_correctness_cls(llm=llm),
    }
    metrics = {
        name: available_metrics[name]
        for name in RAGAS_TARGET_METRICS[evaluation_target]
    }
    try:
        logger.info(
            "industry_ragas_evaluation_started case_count=%s model_name=%s evaluation_target=%s",
            len(rows),
            resolved_model_name,
            evaluation_target,
        )
        case_results: list[IndustryRagasCaseResult] = []
        for row in rows:
            case_results.append(
                await _evaluate_row_with_ragas(
                    row=row,
                    metrics=metrics,
                )
            )
        _ensure_any_metric_succeeded(case_results)
        summary = _summarize_case_results(case_results)
        coverage = _summarize_metric_coverage(summary)
        report = {
            "status": coverage["status"],
            "evaluation_target": evaluation_target,
            "model_name": resolved_model_name,
            "metrics": list(metrics),
            "case_count": len(case_results),
            "scored_metric_count": coverage["scored_metric_count"],
            "skipped_metric_count": coverage["skipped_metric_count"],
            "unavailable_case_count": sum(
                1 for result in case_results if result.unavailable
            ),
            "summary": summary,
            "cases": [result.model_dump(mode="json", exclude_none=True) for result in case_results],
        }
        logger.info(
            "industry_ragas_evaluation_finished case_count=%s unavailable_case_count=%s evaluation_target=%s",
            report["case_count"],
            report["unavailable_case_count"],
            evaluation_target,
        )
        return report
    finally:
        await client.close()


def write_industry_ragas_report(report: dict[str, Any], output_path: str | Path) -> None:
    """평가 리포트를 JSON 파일로 저장한다."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def _load_ragas_runtime() -> RagasRuntime:
    _ensure_ragas_langchain_compatibility()
    try:
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            ContextPrecision,
            ContextRecall,
            FactualCorrectness,
            Faithfulness,
            ResponseGroundedness,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "RAGAS import에 실패했습니다. 설치 누락 또는 의존성 호환성 문제일 수 있습니다. "
            f"original_error={exc!s}"
        ) from exc

    return RagasRuntime(
        llm_factory=llm_factory,
        context_precision_cls=ContextPrecision,
        context_recall_cls=ContextRecall,
        faithfulness_cls=Faithfulness,
        factual_correctness_cls=FactualCorrectness,
        response_groundedness_cls=ResponseGroundedness,
    )


def _ensure_ragas_langchain_compatibility() -> None:
    """ragas가 기대하는 legacy LangChain VertexAI import 경로를 보정한다."""
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return

    try:
        importlib.import_module(module_name)
        return
    except ModuleNotFoundError:
        pass

    vertex_ai_cls = _resolve_vertex_ai_chat_model()
    shim_module = ModuleType(module_name)
    setattr(shim_module, "ChatVertexAI", vertex_ai_cls)
    sys.modules[module_name] = shim_module
    logger.info(
        "ragas_langchain_vertexai_shim_enabled shim_module=%s shim_class=%s",
        module_name,
        getattr(vertex_ai_cls, "__name__", type(vertex_ai_cls).__name__),
    )


def _resolve_vertex_ai_chat_model() -> type[Any]:
    try:
        vertex_ai_module = importlib.import_module("langchain_google_vertexai")
    except ImportError:
        class ChatVertexAI:  # noqa: N801
            """ragas import 호환용 최소 stub."""

        return ChatVertexAI

    chat_vertex_ai = getattr(vertex_ai_module, "ChatVertexAI", None)
    if not isinstance(chat_vertex_ai, type):
        raise RuntimeError(
            "langchain_google_vertexai.ChatVertexAI 클래스를 찾을 수 없습니다."
        )
    return chat_vertex_ai


def build_industry_agent_response_text(business_output: dict[str, Any]) -> str:
    """IndustryAnalystAgent 구조화 출력을 평가용 자연어 응답으로 정규화한다."""
    parts: list[str] = []
    ksic_code = _normalize_optional_str(business_output.get("ksic_code"))
    if ksic_code:
        parts.append(f"업종 분류는 {ksic_code}입니다.")

    industry_summary = _ensure_dict(business_output.get("industry_summary"))
    sector_note = _normalize_optional_str(industry_summary.get("sector_note"))
    if sector_note:
        parts.append(f"산업 특성은 {sector_note}")

    industry_outlook = _ensure_dict(business_output.get("industry_outlook"))
    outlook_score = _normalize_optional_str(industry_outlook.get("outlook_score"))
    if outlook_score:
        parts.append(f"현재 업황 평가는 {outlook_score}입니다.")

    methodology = _ensure_dict(industry_outlook.get("industry_methodology"))
    methodology_summary = _normalize_optional_str(methodology.get("summary"))
    if methodology_summary:
        parts.append(f"신용평가방법론 요약은 {methodology_summary}")

    key_risk_factors = _string_list(methodology.get("key_risk_factors"))
    if key_risk_factors:
        parts.append(
            "핵심 리스크는 "
            + ", ".join(key_risk_factors[:3])
            + "입니다."
        )

    business_cycle = _ensure_dict(business_output.get("business_cycle"))
    phase = _normalize_optional_str(business_cycle.get("phase"))
    if phase:
        parts.append(f"경기 국면은 {phase} 단계입니다.")

    macro_note = _extract_macro_note(_ensure_dict(business_output.get("macro_indicators")))
    if macro_note:
        parts.append(macro_note)

    return " ".join(parts).strip()


@dataclass(slots=True)
class _OfflineIndustryEvalProvider:
    """네트워크 없이 IndustryAnalystAgent의 RAG 경로를 평가하기 위한 provider."""

    case: IndustryAgentRagasEvalCase
    retriever: IndustryMethodologyRetriever
    _base_provider: ToolIndustryDataProvider = field(init=False)

    def __post_init__(self) -> None:
        self._base_provider = ToolIndustryDataProvider()

    def map_corp_to_ksic(self, corp_code: str) -> dict[str, Any]:
        if self.case.ksic_code:
            return {
                "corp_name": self.case.company_name,
                "induty_code": self.case.induty_code or "",
                "ksic_code": self.case.ksic_code,
            }
        return self._base_provider.map_corp_to_ksic(corp_code)

    def get_industry_avg_ratios(
        self,
        ksic_code: str,
        year: int,
        company_ratios: Any,
    ) -> dict[str, Any]:
        return self._base_provider.get_industry_avg_ratios(
            ksic_code,
            year,
            company_ratios,
        )

    def get_industry_outlook(
        self,
        ksic_code: str,
        induty_code: str | None = None,
        company_name: str | None = None,
    ) -> dict[str, Any]:
        rag_result = self.retriever(
            query=self.case.user_input,
            industry_name=None,
            ksic_code=ksic_code,
            sub_sector=self.case.sub_sector,
            include_contexts=True,
        )
        return {
            "outlook_score": "Medium",
            "source": "offline_rag_eval",
            "note": "RAG 평가용 오프라인 업황 기본값",
            **rag_result,
        }

    def get_business_cycle(self) -> dict[str, Any]:
        return {
            "phase": "unknown",
            "signal": "offline_eval",
            "source": "offline_rag_eval",
        }

    def get_macro_indicators(self, ksic_code: str) -> dict[str, Any]:
        return {
            "ksic_code": ksic_code,
            "note": "오프라인 RAG 평가에서는 거시 지표를 생략합니다.",
        }


def _load_agent_retrieved_contexts(
    *,
    case: IndustryAgentRagasEvalCase,
    business_output: dict[str, Any],
    methodology_sources: list[dict[str, Any]],
    retriever: IndustryMethodologyRetriever,
) -> list[str]:
    direct_contexts = _string_list(business_output.get("retrieved_contexts"))
    if direct_contexts:
        logger.info(
            "industry_ragas_agent_contexts_reused case_id=%s context_count=%s",
            case.case_id,
            len(direct_contexts),
        )
        return direct_contexts

    ksic_code = _normalize_optional_str(business_output.get("ksic_code"))
    if not ksic_code:
        logger.info(
            "industry_ragas_agent_contexts_missing_ksic case_id=%s",
            case.case_id,
        )
        return []
    rag_result = retriever(
        query=case.user_input,
        ksic_code=ksic_code,
        sub_sector=_infer_sub_sector_from_sources(methodology_sources),
        include_contexts=True,
    )
    fallback_contexts = _string_list(rag_result.get("retrieved_contexts"))
    logger.info(
        "industry_ragas_agent_contexts_loaded_from_retriever case_id=%s context_count=%s source_hint_count=%s",
        case.case_id,
        len(fallback_contexts),
        len(methodology_sources),
    )
    return fallback_contexts


def _extract_macro_note(macro_indicators: dict[str, Any]) -> str | None:
    for key in ("fx_impact", "note"):
        value = _normalize_optional_str(macro_indicators.get(key))
        if value:
            return f"거시 환경 해석은 {value}"
    return None


def _resolve_agent_eval_error(
    *,
    methodology_error: Any,
    industry_tool_errors: Any,
) -> str | None:
    normalized_methodology_error = _normalize_optional_str(methodology_error)
    if normalized_methodology_error:
        return normalized_methodology_error
    if not isinstance(industry_tool_errors, list) or not industry_tool_errors:
        return None
    first_error = industry_tool_errors[0]
    if not isinstance(first_error, dict):
        return _normalize_optional_str(first_error)
    return _normalize_optional_str(first_error.get("message")) or _normalize_optional_str(
        first_error.get("error_code")
    )


def _infer_sub_sector_from_sources(methodology_sources: list[dict[str, Any]]) -> str | None:
    for source in methodology_sources:
        value = _normalize_optional_str(source.get("sub_sector"))
        if value:
            return value
    return None


async def _evaluate_row_with_ragas(
    *,
    row: IndustryRagasEvalRow,
    metrics: dict[str, Any],
) -> IndustryRagasCaseResult:
    logger.info(
        "industry_ragas_case_evaluation_started case_id=%s retrieved_context_count=%s unavailable=%s",
        row.case_id,
        len(row.retrieved_contexts),
        row.unavailable,
    )
    metric_scores: dict[str, IndustryRagasMetricScore] = {}
    if "context_precision" in metrics:
        metric_scores["context_precision"] = await _score_context_precision(
            metrics["context_precision"],
            row,
        )
    if "context_recall" in metrics:
        metric_scores["context_recall"] = await _score_context_recall(
            metrics["context_recall"],
            row,
        )
    if "faithfulness" in metrics:
        metric_scores["faithfulness"] = await _score_faithfulness(
            metrics["faithfulness"],
            row,
        )
    if "response_groundedness" in metrics:
        metric_scores["response_groundedness"] = await _score_response_groundedness(
            metrics["response_groundedness"],
            row,
        )
    if "factual_correctness" in metrics:
        metric_scores["factual_correctness"] = await _score_factual_correctness(
            metrics["factual_correctness"],
            row,
        )
    logger.info(
        "industry_ragas_case_evaluation_finished case_id=%s scored_metrics=%s skipped_metrics=%s",
        row.case_id,
        sum(1 for score in metric_scores.values() if score.value is not None),
        sum(1 for score in metric_scores.values() if score.skipped is not None),
    )
    return IndustryRagasCaseResult(
        case_id=row.case_id,
        user_input=row.user_input,
        response=row.response,
        reference=row.reference,
        retrieved_contexts=list(row.retrieved_contexts),
        methodology_sources=list(row.methodology_sources),
        unavailable=row.unavailable,
        error=row.error,
        metric_scores=metric_scores,
    )


async def _score_context_precision(metric: Any, row: IndustryRagasEvalRow) -> IndustryRagasMetricScore:
    if not row.retrieved_contexts:
        return _skip_metric("context_precision", row.case_id, "retrieved_contexts 비어 있음")
    return await _run_metric(
        "context_precision",
        metric.ascore(
            user_input=row.user_input,
            reference=row.reference,
            retrieved_contexts=row.retrieved_contexts,
        ),
        row.case_id,
    )


async def _score_context_recall(metric: Any, row: IndustryRagasEvalRow) -> IndustryRagasMetricScore:
    if not row.retrieved_contexts:
        return _skip_metric("context_recall", row.case_id, "retrieved_contexts 비어 있음")
    return await _run_metric(
        "context_recall",
        metric.ascore(
            user_input=row.user_input,
            reference=row.reference,
            retrieved_contexts=row.retrieved_contexts,
        ),
        row.case_id,
    )


async def _score_faithfulness(metric: Any, row: IndustryRagasEvalRow) -> IndustryRagasMetricScore:
    if not row.retrieved_contexts:
        return _skip_metric("faithfulness", row.case_id, "retrieved_contexts 비어 있음")
    if not row.response.strip():
        return _skip_metric("faithfulness", row.case_id, "response 비어 있음")
    return await _run_metric(
        "faithfulness",
        metric.ascore(
            user_input=row.user_input,
            response=row.response,
            retrieved_contexts=row.retrieved_contexts,
        ),
        row.case_id,
    )


async def _score_response_groundedness(
    metric: Any,
    row: IndustryRagasEvalRow,
) -> IndustryRagasMetricScore:
    if not row.retrieved_contexts:
        return _skip_metric(
            "response_groundedness",
            row.case_id,
            "retrieved_contexts 비어 있음",
        )
    if not row.response.strip():
        return _skip_metric("response_groundedness", row.case_id, "response 비어 있음")
    return await _run_metric(
        "response_groundedness",
        metric.ascore(
            response=row.response,
            retrieved_contexts=row.retrieved_contexts,
        ),
        row.case_id,
    )


async def _score_factual_correctness(
    metric: Any,
    row: IndustryRagasEvalRow,
) -> IndustryRagasMetricScore:
    if not row.response.strip():
        return _skip_metric("factual_correctness", row.case_id, "response 비어 있음")
    return await _run_metric(
        "factual_correctness",
        metric.ascore(
            response=row.response,
            reference=row.reference,
        ),
        row.case_id,
    )


async def _run_metric(
    metric_name: str,
    coroutine: Any,
    case_id: str,
) -> IndustryRagasMetricScore:
    logger.info(
        "industry_ragas_metric_started case_id=%s metric_name=%s",
        case_id,
        metric_name,
    )
    try:
        result = await coroutine
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "industry_ragas_metric_failed case_id=%s metric_name=%s error=%s",
            case_id,
            metric_name,
            exc,
        )
        return IndustryRagasMetricScore(skipped=str(exc))

    normalized_value = _normalize_metric_value(getattr(result, "value", None))
    normalized_reason = _normalize_optional_str(getattr(result, "reason", None))
    if normalized_value is None:
        reason = normalized_reason or "metric이 유효한 숫자 점수를 반환하지 않음"
        logger.warning(
            "industry_ragas_metric_invalid case_id=%s metric_name=%s reason=%s",
            case_id,
            metric_name,
            reason,
        )
        return IndustryRagasMetricScore(skipped=reason)
    logger.info(
        "industry_ragas_metric_finished case_id=%s metric_name=%s value=%s has_reason=%s",
        case_id,
        metric_name,
        normalized_value,
        bool(normalized_reason),
    )
    return IndustryRagasMetricScore(
        value=normalized_value,
        reason=normalized_reason,
    )


def _skip_metric(
    metric_name: str,
    case_id: str,
    reason: str,
) -> IndustryRagasMetricScore:
    logger.info(
        "industry_ragas_metric_skipped case_id=%s metric_name=%s reason=%s",
        case_id,
        metric_name,
        reason,
    )
    return IndustryRagasMetricScore(skipped=reason)


def _summarize_case_results(case_results: list[IndustryRagasCaseResult]) -> dict[str, Any]:
    metric_names = [
        metric_name
        for metric_name in RAGAS_METRIC_NAMES
        if any(metric_name in result.metric_scores for result in case_results)
    ]
    summary: dict[str, Any] = {}
    for metric_name in metric_names:
        values = [
            score.value
            for result in case_results
            if (score := result.metric_scores.get(metric_name)) is not None
            and score.value is not None
        ]
        summary[metric_name] = {
            "mean": round(fmean(values), 4) if values else None,
            "scored_cases": len(values),
            "skipped_cases": len(case_results) - len(values),
        }
    return summary


def _ensure_any_metric_succeeded(
    case_results: list[IndustryRagasCaseResult],
) -> None:
    if any(
        score.value is not None
        for result in case_results
        for score in result.metric_scores.values()
    ):
        return

    reasons = sorted(
        {
            score.skipped
            for result in case_results
            for score in result.metric_scores.values()
            if score.skipped
        }
    )
    details = "; ".join(reasons) if reasons else "metric 결과 없음"
    raise RuntimeError(
        "RAGAS metric 점수를 하나도 생성하지 못했습니다. "
        f"evaluator 연결과 모델 설정을 확인해 주세요. details={details}"
    )


def _summarize_metric_coverage(summary: dict[str, Any]) -> dict[str, Any]:
    scored_metric_count = sum(
        int(metric_summary.get("scored_cases", 0))
        for metric_summary in summary.values()
    )
    skipped_metric_count = sum(
        int(metric_summary.get("skipped_cases", 0))
        for metric_summary in summary.values()
    )
    return {
        "status": "complete" if skipped_metric_count == 0 else "partial",
        "scored_metric_count": scored_metric_count,
        "skipped_metric_count": skipped_metric_count,
    }


def _normalize_metric_value(value: Any) -> float | None:
    if value is None:
        return None
    normalized = float(value)
    if not math.isfinite(normalized):
        return None
    return round(normalized, 4)


def _normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _load_jsonl_cases(
    dataset_path: str | Path,
    model_class: type[_EvalCaseT],
) -> list[_EvalCaseT]:
    path = _resolve_dataset_path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(
            f"평가셋 파일을 찾을 수 없습니다: {path}. "
            "실행 가능한 예시는 "
            "`backend/rag/eval_datasets/industry_methodology.sample.jsonl` 또는 "
            "`backend/rag/eval_datasets/industry_agent.sample.jsonl` 를 참고해 주세요."
        )
    lines = path.read_text(encoding="utf-8").splitlines()
    cases: list[_EvalCaseT] = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{path} {line_number}번째 줄 JSON 파싱 실패: {exc.msg}"
            ) from exc
        cases.append(model_class.model_validate(payload))
    logger.info(
        "industry_ragas_dataset_loaded path=%s case_count=%s model_class=%s",
        path,
        len(cases),
        model_class.__name__,
    )
    return cases


def _resolve_dataset_path(dataset_path: str | Path) -> Path:
    path = Path(dataset_path)
    if path.exists() or path.is_absolute():
        return path
    repo_relative_path = PROJECT_ROOT / path
    if repo_relative_path.exists():
        return repo_relative_path
    return path


def _validate_rag_eval_rows(
    rows: list[IndustryRagasEvalRow],
    *,
    evaluation_target: EvaluationTarget,
) -> None:
    if not rows:
        raise ValueError("평가할 row가 없습니다.")

    missing_context_case_ids = [
        row.case_id for row in rows if not row.retrieved_contexts
    ]
    if len(missing_context_case_ids) != len(rows):
        return

    unavailable_errors = sorted(
        {
            row.error
            for row in rows
            if row.unavailable and row.error
        }
    )
    details = ", ".join(unavailable_errors) if unavailable_errors else "retrieved_contexts 없음"
    raise RuntimeError(
        "RAG 평가에 필요한 retrieved_contexts를 하나도 확보하지 못했습니다. "
        f"evaluation_target={evaluation_target} case_ids={missing_context_case_ids} "
        f"details={details}. "
        "ChromaDB/벡터스토어 준비 상태와 industry RAG 인덱스 적재 여부를 먼저 확인해 주세요."
    )
