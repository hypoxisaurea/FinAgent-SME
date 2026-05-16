"""Multimodal Document Agent LangGraph 워크플로우

노드 순서:
  1. extract_text   — M-001 PDF 텍스트 추출 및 섹션 분류
  2. parse_tables   — M-002 재무 테이블 파싱 (재무 섹션 페이지만)
  3. interpret_charts — M-003 차트·그래프 해석 (병렬)
  4. summarize      — M-004 문서 전체 요약
  5. aggregate      — 최종 결과 조립
"""

from __future__ import annotations

from datetime import date
from typing import Any

from langgraph.graph import StateGraph, END

from .handlers.pdf_text_extractor import extract_pdf_text
from .handlers.table_parser import parse_financial_tables
from .handlers.chart_interpreter import interpret_charts
from .handlers.document_summarizer import summarize_document
from .models import MultimodalDocumentResult, SectionType


MultimodalState = dict[str, Any]


# ─── 노드 1: PDF 텍스트 추출 ──────────────────────────────────────────────────

async def _extract_text(state: MultimodalState) -> MultimodalState:
    pdf_source = state.get("pdf_bytes") or state.get("pdf_path", "")
    errors: list[str] = []

    try:
        sections, total_pages = extract_pdf_text(pdf_source)
    except Exception as e:
        sections, total_pages = [], 0
        errors.append(f"extract_text: {e}")

    return {**state, "sections": sections, "total_pages": total_pages, "errors": errors}


# ─── 노드 2: 재무 테이블 파싱 ─────────────────────────────────────────────────

async def _parse_tables(state: MultimodalState) -> MultimodalState:
    pdf_source = state.get("pdf_bytes") or state.get("pdf_path", "")
    sections = state.get("sections", [])
    errors: list[str] = state.get("errors", [])

    # 재무 섹션 페이지 번호 추출
    financial_pages = [
        p
        for s in sections
        if s.section_type == SectionType.FINANCIAL
        for p in range(s.page_start, s.page_end + 1)
    ]

    tables = []
    if financial_pages and pdf_source:
        try:
            tables = await parse_financial_tables(pdf_source, financial_pages)
        except Exception as e:
            errors.append(f"parse_tables: {e}")

    return {**state, "tables": tables, "errors": errors}


# ─── 노드 3: 차트 해석 ────────────────────────────────────────────────────────

async def _interpret_charts(state: MultimodalState) -> MultimodalState:
    pdf_source = state.get("pdf_bytes") or state.get("pdf_path", "")
    total_pages = state.get("total_pages", 0)
    errors: list[str] = state.get("errors", [])

    charts = []
    if pdf_source and total_pages > 0:
        all_pages = list(range(1, total_pages + 1))
        try:
            charts = await interpret_charts(pdf_source, all_pages)
        except Exception as e:
            errors.append(f"interpret_charts: {e}")

    return {**state, "charts": charts, "errors": errors}


# ─── 노드 4: 문서 요약 ────────────────────────────────────────────────────────

async def _summarize(state: MultimodalState) -> MultimodalState:
    company_name = state.get("company_name", "")
    sections = state.get("sections", [])
    errors: list[str] = state.get("errors", [])

    summary = None
    if sections:
        try:
            summary = await summarize_document(company_name, sections)
        except Exception as e:
            errors.append(f"summarize: {e}")

    return {**state, "summary": summary, "errors": errors}


# ─── 노드 5: 최종 집계 ────────────────────────────────────────────────────────

async def _aggregate(state: MultimodalState) -> MultimodalState:
    result = MultimodalDocumentResult(
        company_name=state.get("company_name", ""),
        corp_code=state.get("corp_code", ""),
        pdf_path=state.get("pdf_path"),
        total_pages=state.get("total_pages", 0),
        sections=state.get("sections", []),
        tables=state.get("tables", []),
        charts=state.get("charts", []),
        summary=state.get("summary"),
        processed_at=date.today(),
        processing_errors=state.get("errors", []),
    )
    return {**state, "final_result": result}


# ─── 그래프 빌드 ──────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(MultimodalState)
    g.add_node("extract_text",      _extract_text)
    g.add_node("parse_tables",      _parse_tables)
    g.add_node("interpret_charts",  _interpret_charts)
    g.add_node("summarize",         _summarize)
    g.add_node("aggregate",         _aggregate)

    g.set_entry_point("extract_text")
    g.add_edge("extract_text",     "parse_tables")
    g.add_edge("parse_tables",     "interpret_charts")
    g.add_edge("interpret_charts", "summarize")
    g.add_edge("summarize",        "aggregate")
    g.add_edge("aggregate",        END)

    return g.compile()


multimodal_graph = _build_graph()


# ─── 공개 진입점 ──────────────────────────────────────────────────────────────

async def run_multimodal_document_agent(
    company_name: str,
    corp_code:    str,
    pdf_bytes:    bytes | None = None,
    pdf_path:     str | None   = None,
) -> MultimodalDocumentResult:
    """Multimodal Document Agent 실행 진입점."""
    initial_state: MultimodalState = {
        "company_name": company_name,
        "corp_code":    corp_code,
        "pdf_bytes":    pdf_bytes,
        "pdf_path":     pdf_path,
    }
    final_state = await multimodal_graph.ainvoke(initial_state)
    return final_state["final_result"]
