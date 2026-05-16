"""Multimodal Document Agent Pydantic 모델"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── 열거형 ──────────────────────────────────────────────────────────────────

class SectionType(str, Enum):
    COVER         = "cover"           # 표지
    TOC           = "toc"             # 목차
    BUSINESS      = "business"        # 사업 개요
    FINANCIAL     = "financial"       # 재무 정보
    RISK          = "risk"            # 위험 요소
    AUDIT         = "audit"           # 감사 보고서
    OTHER         = "other"           # 기타


class TableType(str, Enum):
    INCOME_STATEMENT  = "income_statement"   # 손익계산서
    BALANCE_SHEET     = "balance_sheet"      # 대차대조표
    CASH_FLOW         = "cash_flow"          # 현금흐름표
    UNKNOWN           = "unknown"


# ─── 핸들러별 출력 ────────────────────────────────────────────────────────────

class DocumentSection(BaseModel):
    """M-001 추출된 텍스트 섹션"""
    section_type: SectionType
    page_start:   int
    page_end:     int
    text:         str
    char_count:   int


class ExtractedTable(BaseModel):
    """M-002 파싱된 재무 테이블"""
    table_type:   TableType
    page_number:  int
    headers:      list[str]
    rows:         list[dict]          # {컬럼명: 값} 형태
    raw_text:     str                 # 원본 텍스트 (fallback용)
    confidence:   float = 1.0        # 0~1, Claude Vision 파싱 신뢰도


class ExtractedChart(BaseModel):
    """M-003 해석된 차트·그래프"""
    page_number:  int
    chart_title:  str
    description:  str                 # Claude Vision 해석 결과
    data_points:  list[dict]          # 수치 추출 결과 (가능한 경우)
    raw_caption:  Optional[str] = None


class DocumentSummary(BaseModel):
    """M-004 문서 요약"""
    company_name:     str
    report_year:      Optional[int]  = None
    business_summary: str            # 사업 개요 요약
    financial_summary: str           # 재무 현황 요약
    risk_summary:     str            # 위험 요소 요약
    key_points:       list[str]      # 핵심 포인트 3~5개


# ─── 최종 출력 ────────────────────────────────────────────────────────────────

class MultimodalDocumentResult(BaseModel):
    """Multimodal Document Agent 최종 출력"""
    company_name: str
    corp_code:    str
    pdf_path:     Optional[str]   = None
    total_pages:  int             = 0

    # 핸들러별 결과
    sections:     list[DocumentSection] = Field(default_factory=list)  # M-001
    tables:       list[ExtractedTable]  = Field(default_factory=list)  # M-002
    charts:       list[ExtractedChart]  = Field(default_factory=list)  # M-003
    summary:      Optional[DocumentSummary] = None                     # M-004

    # 상태
    processed_at:      date      = Field(default_factory=date.today)
    processing_errors: list[str] = Field(default_factory=list)
