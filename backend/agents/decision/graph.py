"""Decision Agent LangGraph 워크플로우

흐름:
  grade_calculation → decision_making → limit_recommendation → explanation → aggregate
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from langgraph.graph import StateGraph, END

from .handlers.grade_calculator import calculate_grade
from .handlers.decision_maker import make_decision
from .handlers.limit_recommender import recommend_limit
from .handlers.explanation_generator import generate_explanation
from .models import DecisionOutput

logger = logging.getLogger(__name__)

DecisionState = dict[str, Any]


# ─── 노드 1: 신용등급 산출 (D-001) ───────────────────────────────────────────

async def _grade_calculation(state: DecisionState) -> DecisionState:
    try:
        grade_result = calculate_grade(state)
    except Exception as exc:
        logger.error("[%s] 등급 산출 실패: %s", state.get("company_name"), exc)
        state.setdefault("errors", []).append(f"grade_calculation: {exc}")
        grade_result = None

    return {**state, "grade_result": grade_result}


# ─── 노드 2: 승인·거절 판단 (D-002) ──────────────────────────────────────────

async def _decision_making(state: DecisionState) -> DecisionState:
    grade_result = state.get("grade_result")
    if grade_result is None:
        state.setdefault("errors", []).append("decision_making: grade_result 없음")
        return {**state, "decision_result": None}

    try:
        decision_result = make_decision(
            grade=grade_result.grade,
            score=grade_result.score,
            context=state,
        )
    except Exception as exc:
        logger.error("[%s] 판단 실패: %s", state.get("company_name"), exc)
        state.setdefault("errors", []).append(f"decision_making: {exc}")
        decision_result = None

    return {**state, "decision_result": decision_result}


# ─── 노드 3: 한도 추천 (D-003) ───────────────────────────────────────────────

async def _limit_recommendation(state: DecisionState) -> DecisionState:
    grade_result    = state.get("grade_result")
    decision_result = state.get("decision_result")

    if grade_result is None or decision_result is None:
        state.setdefault("errors", []).append("limit_recommendation: 선행 결과 없음")
        return {**state, "limit_result": None}

    try:
        limit_result = recommend_limit(
            grade=grade_result.grade,
            decision=decision_result.result,
            context=state,
        )
    except Exception as exc:
        logger.error("[%s] 한도 추천 실패: %s", state.get("company_name"), exc)
        state.setdefault("errors", []).append(f"limit_recommendation: {exc}")
        limit_result = None

    return {**state, "limit_result": limit_result}


# ─── 노드 4: 자연어 설명 생성 (D-004) ────────────────────────────────────────

async def _explanation(state: DecisionState) -> DecisionState:
    grade_result    = state.get("grade_result")
    decision_result = state.get("decision_result")
    limit_result    = state.get("limit_result")

    if not all([grade_result, decision_result, limit_result]):
        state.setdefault("errors", []).append("explanation: 선행 결과 없음")
        return {**state, "explanation_result": None}

    try:
        explanation_result = await generate_explanation(
            company_name=state.get("company_name", ""),
            grade_result=grade_result,
            decision=decision_result.result,
            limit_result=limit_result,
            reasons=decision_result.reasons,
            context=state,
        )
    except Exception as exc:
        logger.error("[%s] 설명 생성 실패: %s", state.get("company_name"), exc)
        state.setdefault("errors", []).append(f"explanation: {exc}")
        explanation_result = None

    return {**state, "explanation_result": explanation_result}


# ─── 노드 5: 최종 집계 ───────────────────────────────────────────────────────

async def _aggregate(state: DecisionState) -> DecisionState:
    grade_result    = state.get("grade_result")
    decision_result = state.get("decision_result")
    limit_result    = state.get("limit_result")

    if not grade_result or not decision_result:
        # 최소 결과도 없으면 에러 반환
        error_output = {
            "decision_output": None,
            "decision_errors": state.get("errors", []),
        }
        return {**state, **error_output}

    output = DecisionOutput(
        company_name=state.get("company_name", ""),
        corp_code=state.get("corp_code", ""),

        grade=grade_result.grade,
        grade_score=grade_result.score,

        decision=decision_result.result,
        confidence=decision_result.confidence,
        reasons=decision_result.reasons,

        recommended_limit=limit_result.recommended_limit if limit_result else None,
        limit_range=limit_result.limit_range       if limit_result else None,
        limit_basis=limit_result.limit_basis       if limit_result else "",

        explanation=state.get("explanation_result"),
        grade_detail=grade_result,

        processed_at=date.today(),
        processing_errors=state.get("errors", []),
    )

    logger.info(
        "decision_aggregated company=%s grade=%s decision=%s score=%d",
        output.company_name,
        output.grade.value,
        output.decision.value,
        output.grade_score,
    )

    return {**state, "decision_output": output}


# ─── 그래프 빌드 ──────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(DecisionState)

    g.add_node("grade_calculation",    _grade_calculation)
    g.add_node("decision_making",      _decision_making)
    g.add_node("limit_recommendation", _limit_recommendation)
    g.add_node("explanation",          _explanation)
    g.add_node("aggregate",            _aggregate)

    g.set_entry_point("grade_calculation")
    g.add_edge("grade_calculation",    "decision_making")
    g.add_edge("decision_making",      "limit_recommendation")
    g.add_edge("limit_recommendation", "explanation")
    g.add_edge("explanation",          "aggregate")
    g.add_edge("aggregate",            END)

    return g.compile()


decision_graph = _build_graph()


async def run_decision_agent(payload: dict[str, Any]) -> DecisionOutput | None:
    """Decision Agent 워크플로우를 실행하고 최종 출력을 반환한다."""
    final_state = await decision_graph.ainvoke(payload)
    return final_state.get("decision_output")