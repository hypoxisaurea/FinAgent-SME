"""Risk Event Agent LangGraph 워크플로우

수정 사항:
- 동기 핸들러를 asyncio.to_thread()로 스레드풀에서 실행 → 진짜 병렬 처리
- 에러별 로깅 추가
- CRITICAL 이벤트 원인 추적 (critical_events, critical_reasons) 추가
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date
from typing import Any

from backend.agents.risk_event.data.sme_loader import get_financial_rows
from backend.agents.risk_event.handlers.disclosure_detector import (
    detect_disclosure_anomalies,
)
from backend.agents.risk_event.handlers.financial_anomaly_detector import (
    detect_financial_anomalies,
)
from backend.agents.risk_event.handlers.keyword_detector import detect_keywords
from backend.agents.risk_event.handlers.legal_risk_detector import detect_legal_risks
from backend.agents.risk_event.handlers.sentiment_analyzer import analyze_sentiment
from backend.agents.risk_event.handlers.severity_classifier import classify_severity
from backend.agents.risk_event.handlers.timeline_builder import build_timeline
from backend.agents.risk_event.models import (
    RiskEvent,
    RiskEventResult,
    SeverityClassifiedEvent,
    SeverityLevel,
)
from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)
RiskEventState = dict[str, Any]


# ─── 노드 1: 병렬 핸들러 ─────────────────────────────────────────────────────

async def _parallel_handlers(state: RiskEventState) -> RiskEventState:
    """5개 핸들러를 병렬 실행한다.

    동기 함수(keyword, disclosure, legal, financial)는 asyncio.to_thread()로
    스레드풀에서 실행해 진짜 병렬 처리를 보장한다.
    비동기 함수(sentiment)는 그대로 await한다.
    """
    company_name    = state["company_name"]
    corp_code       = state["corp_code"]
    request_id      = state.get("request_id")
    news_data       = state.get("news_data", [])
    disclosure_data = state.get("disclosure_data", [])
    court_data      = state.get("court_data", [])
    logger.info(
        "[%s] risk_event_parallel_handlers_started corp_code=%s news_count=%s disclosure_count=%s court_count=%s",
        company_name,
        corp_code,
        len(news_data),
        len(disclosure_data),
        len(court_data),
    )
    financial_rows = await asyncio.to_thread(get_financial_rows, corp_code)
    logger.info(
        "[%s] risk_event_financial_rows_loaded corp_code=%s row_count=%s",
        company_name,
        corp_code,
        len(financial_rows),
    )

    results = await asyncio.gather(
        # 동기 함수 → 스레드풀
        asyncio.to_thread(detect_keywords, company_name, news_data, disclosure_data),
        # 비동기 함수 → 그대로
        analyze_sentiment(company_name, news_data, request_id=request_id),
        # 동기 함수 → 스레드풀
        asyncio.to_thread(detect_disclosure_anomalies, company_name, corp_code, disclosure_data),
        asyncio.to_thread(detect_legal_risks, company_name, court_data),
        asyncio.to_thread(detect_financial_anomalies, company_name, corp_code, financial_rows),
        return_exceptions=True,
    )

    labels = ["keyword", "sentiment", "disclosure", "legal", "financial"]
    handler_results = {}
    all_events: list[RiskEvent] = []
    errors: list[str] = []

    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            logger.error("[%s] %s 핸들러 실패: %s", company_name, label, result)
            errors.append(f"{label}: {type(result).__name__}: {result}")
            handler_results[label] = None
            continue

        handler_results[label] = result

        # 핸들러별 이벤트 수집
        events = (
            getattr(result, "detected_events", None)
            or getattr(result, "anomalies", None)
            or getattr(result, "legal_risks", None)
            or []
        )
        logger.info(
            "[%s] risk_event_handler_completed handler=%s event_count=%s",
            company_name,
            label,
            len(events),
        )
        all_events.extend(events)

    logger.info(
        "[%s] risk_event_parallel_handlers_finished total_event_count=%s error_count=%s",
        company_name,
        len(all_events),
        len(errors),
    )
    return {
        **state,
        "keyword_result":    handler_results["keyword"],
        "sentiment_result":  handler_results["sentiment"],
        "disclosure_result": handler_results["disclosure"],
        "legal_result":      handler_results["legal"],
        "financial_result":  handler_results["financial"],
        "all_events":        all_events,
        "errors":            errors,
    }


# ─── 노드 2: 심각도 분류 (R-004) ──────────────────────────────────────────────

async def _classify_severity(state: RiskEventState) -> RiskEventState:
    classified = [classify_severity(ev) for ev in state.get("all_events", [])]
    logger.info(
        "[%s] risk_event_classify_severity_finished classified_count=%s",
        state["company_name"],
        len(classified),
    )
    return {**state, "classified_events": classified}


# ─── 노드 3: 타임라인 생성 (R-005) ────────────────────────────────────────────

async def _build_timeline(state: RiskEventState) -> RiskEventState:
    timeline = build_timeline(state.get("classified_events", []))
    logger.info(
        "[%s] risk_event_timeline_finished timeline_count=%s",
        state["company_name"],
        len(timeline),
    )
    return {**state, "timeline": timeline}


# ─── CRITICAL 원인 추출 (신규) ─────────────────────────────────────────────────

def _extract_critical_info(
    classified: list[SeverityClassifiedEvent],
) -> tuple[list[SeverityClassifiedEvent], list[str]]:
    """심각도 분류된 이벤트 목록에서 CRITICAL 등급만 추출해
    상세 객체 목록과, 사람이 바로 읽을 수 있는 원인 문자열 목록을 반환한다.
    """
    critical_events = [e for e in classified if e.severity == SeverityLevel.CRITICAL]
    critical_reasons = [
        f"[{e.event.title}] {e.event.description} (근거: {e.rationale})"
        for e in critical_events
    ]
    return critical_events, critical_reasons


# ─── 노드 4: 최종 집계 ────────────────────────────────────────────────────────

async def _aggregate(state: RiskEventState) -> RiskEventState:
    classified: list[SeverityClassifiedEvent] = state.get("classified_events", [])
    count = Counter(e.severity for e in classified)

    if count[SeverityLevel.CRITICAL] > 0:
        overall = SeverityLevel.CRITICAL
    elif count[SeverityLevel.HIGH] > 0:
        overall = SeverityLevel.HIGH
    elif count[SeverityLevel.MEDIUM] > 0:
        overall = SeverityLevel.MEDIUM
    else:
        overall = SeverityLevel.LOW

    critical_events, critical_reasons = _extract_critical_info(classified)
    financial_result = state.get("financial_result")

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
        timeline=state.get("timeline", []),
        critical_count=count[SeverityLevel.CRITICAL],
        high_count=count[SeverityLevel.HIGH],
        medium_count=count[SeverityLevel.MEDIUM],
        low_count=count[SeverityLevel.LOW],
        total_event_count=len(classified),
        overall_risk_level=overall,
        critical_events=critical_events,
        critical_reasons=critical_reasons,
        latest_debt_ratio=getattr(financial_result, "latest_debt_ratio", None),
        latest_op_margin=getattr(financial_result, "latest_op_margin", None),
        is_net_income_negative=getattr(financial_result, "is_net_income_negative", False),
        processed_at=date.today(),
        processing_errors=state.get("errors", []),
    )
    logger.info(
        "[%s] risk_event_aggregate_finished total_event_count=%s overall_risk_level=%s processing_error_count=%s",
        state["company_name"],
        result.total_event_count,
        result.overall_risk_level.value,
        len(result.processing_errors),
    )
    return {**state, "final_result": result}


# ─── 그래프 빌드 ──────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(RiskEventState)
    g.add_node("parallel_handlers", _parallel_handlers)
    g.add_node("classify_severity", _classify_severity)
    g.add_node("build_timeline",    _build_timeline)
    g.add_node("aggregate",         _aggregate)

    g.set_entry_point("parallel_handlers")
    g.add_edge("parallel_handlers", "classify_severity")
    g.add_edge("classify_severity", "build_timeline")
    g.add_edge("build_timeline",    "aggregate")
    g.add_edge("aggregate",         END)
    return g.compile()


risk_event_graph = _build_graph()


async def run_risk_event_agent(
    company_name:    str,
    corp_code:       str,
    news_data:       list[dict],
    disclosure_data: list[dict],
    court_data:      list[dict],
    request_id:      str | None = None,
) -> RiskEventResult:
    final_state = await risk_event_graph.ainvoke({
        "company_name":    company_name,
        "corp_code":       corp_code,
        "news_data":       news_data,
        "disclosure_data": disclosure_data,
        "court_data":      court_data,
        "request_id":      request_id,
    })
    return final_state["final_result"]
