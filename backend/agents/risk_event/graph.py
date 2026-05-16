"""Risk Event Agent LangGraph 워크플로우

노드 순서:
  1. parallel_handlers  — 5개 핸들러 병렬 실행
  2. classify_severity  — R-004 심각도 분류
  3. build_timeline     — R-005 타임라인 생성
  4. aggregate          — 최종 결과 조립
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date
from typing import Any

from langgraph.graph import StateGraph, END

from .data.sme_loader import get_financial_rows
from .handlers.keyword_detector import detect_keywords
from .handlers.sentiment_analyzer import analyze_sentiment
from .handlers.disclosure_detector import detect_disclosure_anomalies
from .handlers.legal_risk_detector import detect_legal_risks
from .handlers.financial_anomaly_detector import detect_financial_anomalies
from .handlers.severity_classifier import classify_severity
from .handlers.timeline_builder import build_timeline
from .models import (
    RiskEvent, RiskEventResult, SeverityClassifiedEvent,
    SeverityLevel, TimelineEntry,
)


# ─── 상태 타입 ────────────────────────────────────────────────────────────────

RiskEventState = dict[str, Any]


# ─── 노드 1: 병렬 핸들러 ─────────────────────────────────────────────────────

async def _parallel_handlers(state: RiskEventState) -> RiskEventState:
    """5개 핸들러를 asyncio.gather로 병렬 실행한다."""
    company_name    = state["company_name"]
    corp_code       = state["corp_code"]
    news_data       = state.get("news_data", [])
    disclosure_data = state.get("disclosure_data", [])
    court_data      = state.get("court_data", [])

    # financial_features.csv에서 해당 기업 재무 데이터 로드
    financial_rows = get_financial_rows(corp_code)

    async def _run_keyword():
        try:
            return detect_keywords(company_name, news_data, disclosure_data)
        except Exception as e:
            return None, str(e)

    async def _run_sentiment():
        try:
            return await analyze_sentiment(company_name, news_data)
        except Exception as e:
            return None, str(e)

    async def _run_disclosure():
        try:
            return detect_disclosure_anomalies(company_name, corp_code, disclosure_data)
        except Exception as e:
            return None, str(e)

    async def _run_legal():
        try:
            return detect_legal_risks(company_name, court_data)
        except Exception as e:
            return None, str(e)

    async def _run_financial():
        try:
            return detect_financial_anomalies(company_name, corp_code, financial_rows)
        except Exception as e:
            return None, str(e)

    results = await asyncio.gather(
        _run_keyword(),
        _run_sentiment(),
        _run_disclosure(),
        _run_legal(),
        _run_financial(),
        return_exceptions=True,
    )

    keyword_result, sentiment_result, disclosure_result, legal_result, financial_result = results

    # 전체 이벤트 수집
    all_events: list[RiskEvent] = []
    errors: list[str] = []

    for label, result in [
        ("keyword",    keyword_result),
        ("sentiment",  sentiment_result),
        ("disclosure", disclosure_result),
        ("legal",      legal_result),
        ("financial",  financial_result),
    ]:
        if isinstance(result, Exception):
            errors.append(f"{label}: {result}")
            continue
        if result is None:
            continue
        # 각 핸들러 결과에서 이벤트 추출
        events = getattr(result, "detected_events", None) \
              or getattr(result, "anomalies", None) \
              or getattr(result, "legal_risks", None) \
              or []
        all_events.extend(events)

    return {
        **state,
        "keyword_result":    keyword_result,
        "sentiment_result":  sentiment_result,
        "disclosure_result": disclosure_result,
        "legal_result":      legal_result,
        "financial_result":  financial_result,
        "all_events":        all_events,
        "errors":            errors,
    }


# ─── 노드 2: 심각도 분류 (R-004) ──────────────────────────────────────────────

async def _classify_severity(state: RiskEventState) -> RiskEventState:
    all_events: list[RiskEvent] = state.get("all_events", [])
    classified = [classify_severity(ev) for ev in all_events]
    return {**state, "classified_events": classified}


# ─── 노드 3: 타임라인 생성 (R-005) ────────────────────────────────────────────

async def _build_timeline(state: RiskEventState) -> RiskEventState:
    classified: list[SeverityClassifiedEvent] = state.get("classified_events", [])
    timeline = build_timeline(classified)
    return {**state, "timeline": timeline}


# ─── 노드 4: 최종 집계 ────────────────────────────────────────────────────────

async def _aggregate(state: RiskEventState) -> RiskEventState:
    classified: list[SeverityClassifiedEvent] = state.get("classified_events", [])
    timeline:   list[TimelineEntry]           = state.get("timeline", [])

    count = Counter(e.severity for e in classified)
    if count[SeverityLevel.CRITICAL] > 0:
        overall = SeverityLevel.CRITICAL
    elif count[SeverityLevel.HIGH] > 0:
        overall = SeverityLevel.HIGH
    elif count[SeverityLevel.MEDIUM] > 0:
        overall = SeverityLevel.MEDIUM
    else:
        overall = SeverityLevel.LOW

    # 재무 이상 결과에서 Decision Agent 연동용 지표 추출
    financial_result = state.get("financial_result")
    latest_debt_ratio      = getattr(financial_result, "latest_debt_ratio", None)
    latest_op_margin       = getattr(financial_result, "latest_op_margin", None)
    is_net_income_negative = getattr(financial_result, "is_net_income_negative", False)

    result = RiskEventResult(
        company_name=state["company_name"],
        corp_code=state["corp_code"],
        keyword_result=state.get("keyword_result"),
        sentiment_result=state.get("sentiment_result"),
        disclosure_result=state.get("disclosure_result"),
        legal_result=state.get("legal_result"),
        financial_result=financial_result,
        all_events=state.get("all_events", []),
        classified_events=classified,
        timeline=timeline,
        critical_count=count[SeverityLevel.CRITICAL],
        high_count=count[SeverityLevel.HIGH],
        medium_count=count[SeverityLevel.MEDIUM],
        low_count=count[SeverityLevel.LOW],
        total_event_count=len(classified),
        overall_risk_level=overall,
        latest_debt_ratio=latest_debt_ratio,
        latest_op_margin=latest_op_margin,
        is_net_income_negative=is_net_income_negative,
        processed_at=date.today(),
        processing_errors=state.get("errors", []),
    )
    return {**state, "final_result": result}


# ─── 그래프 빌드 ──────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(RiskEventState)
    g.add_node("parallel_handlers",  _parallel_handlers)
    g.add_node("classify_severity",  _classify_severity)
    g.add_node("build_timeline",     _build_timeline)
    g.add_node("aggregate",          _aggregate)

    g.set_entry_point("parallel_handlers")
    g.add_edge("parallel_handlers", "classify_severity")
    g.add_edge("classify_severity", "build_timeline")
    g.add_edge("build_timeline",    "aggregate")
    g.add_edge("aggregate",         END)

    return g.compile()


risk_event_graph = _build_graph()


# ─── 공개 진입점 ──────────────────────────────────────────────────────────────

async def run_risk_event_agent(
    company_name:    str,
    corp_code:       str,
    news_data:       list[dict],
    disclosure_data: list[dict],
    court_data:      list[dict],
) -> RiskEventResult:
    """Risk Event Agent 실행 진입점.

    financial_features.csv 로드는 graph 내부(sme_loader)에서 자동 처리한다.
    """
    initial_state: RiskEventState = {
        "company_name":    company_name,
        "corp_code":       corp_code,
        "news_data":       news_data,
        "disclosure_data": disclosure_data,
        "court_data":      court_data,
    }
    final_state = await risk_event_graph.ainvoke(initial_state)
    return final_state["final_result"]
