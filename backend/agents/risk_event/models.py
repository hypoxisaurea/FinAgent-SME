"""Risk Event Agent Pydantic 모델

입력 스키마, 핸들러 출력, 최종 결과 모두 여기서 정의한다.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── 열거형 ──────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    NEGATIVE_KEYWORD   = "negative_keyword"     # R-001
    NEGATIVE_SENTIMENT = "negative_sentiment"   # R-002
    DISCLOSURE_ANOMALY = "disclosure_anomaly"   # R-003
    LEGAL_RISK         = "legal_risk"           # R-006
    FINANCIAL_ANOMALY  = "financial_anomaly"    # 신규 (financial_features.csv)


class EventSource(str, Enum):
    NEWS           = "news"
    DISCLOSURE     = "disclosure"
    COURT          = "court"
    FINANCIAL_DATA = "financial_data"   # CSV / DB 재무 데이터


class SeverityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEUTRAL  = "neutral"
    NEGATIVE = "negative"


# ─── 공통 이벤트 ─────────────────────────────────────────────────────────────

class RiskEvent(BaseModel):
    """핸들러가 공통으로 반환하는 리스크 이벤트 단위"""
    event_type:  EventType
    source:      EventSource
    title:       str
    description: str
    detected_at: date
    url:         Optional[str]   = None   # 뉴스/공시 원문 링크
    raw_value:   Optional[float] = None   # 재무 수치 등
    delta_value: Optional[float] = None   # YoY 변화량


# ─── 핸들러별 출력 ────────────────────────────────────────────────────────────

class KeywordDetectionResult(BaseModel):
    """R-001 부정 키워드 탐지 결과"""
    company_name:   str
    detected_events: list[RiskEvent]
    analyzed_at:    date


class SentimentAnalysisResult(BaseModel):
    """R-002 감성 분석 결과"""
    company_name:      str
    news_items:        list[dict]
    negative_count:    int
    neutral_count:     int
    positive_count:    int
    overall_sentiment: SentimentLabel
    detected_events:   list[RiskEvent]


class DisclosureAnomalyResult(BaseModel):
    """R-003 공시 이상 탐지 결과"""
    company_name: str
    corp_code:    str
    anomalies:    list[RiskEvent]
    analyzed_at:  date


class LegalRiskResult(BaseModel):
    """R-006 법적 리스크 탐지 결과"""
    company_name: str
    legal_risks:  list[RiskEvent]
    analyzed_at:  date


class FinancialAnomalyResult(BaseModel):
    """재무 이상 징후 탐지 결과 (financial_features.csv 연동)"""
    company_name:           str
    corp_code:              str
    anomalies:              list[RiskEvent] = Field(default_factory=list)
    analyzed_at:            date            = Field(default_factory=date.today)
    years_analyzed:         list[int]       = Field(default_factory=list)
    latest_debt_ratio:      Optional[float] = None
    latest_op_margin:       Optional[float] = None
    is_net_income_negative: bool            = False


# ─── 심각도 분류 / 타임라인 ───────────────────────────────────────────────────

class SeverityClassifiedEvent(BaseModel):
    """R-004 심각도 분류된 이벤트"""
    event:     RiskEvent
    severity:  SeverityLevel
    score:     int           # 0-100
    rationale: str           # 분류 근거


class TimelineEntry(BaseModel):
    """R-005 타임라인 엔트리 (날짜별 이벤트 묶음)"""
    date:   date
    events: list[SeverityClassifiedEvent]


# ─── 최종 출력 ────────────────────────────────────────────────────────────────

class RiskEventResult(BaseModel):
    """Risk Event Agent 최종 출력 스키마"""
    company_name: str
    corp_code:    str

    # 핸들러별 원시 결과
    keyword_result:   Optional[KeywordDetectionResult]  = None
    sentiment_result: Optional[SentimentAnalysisResult] = None
    disclosure_result: Optional[DisclosureAnomalyResult] = None
    legal_result:     Optional[LegalRiskResult]          = None
    financial_result: Optional[FinancialAnomalyResult]  = None  # 신규

    # 통합 결과
    all_events:        list[RiskEvent]               = Field(default_factory=list)
    classified_events: list[SeverityClassifiedEvent] = Field(default_factory=list)
    timeline:          list[TimelineEntry]            = Field(default_factory=list)

    # 요약 통계
    critical_count:     int = 0
    high_count:         int = 0
    medium_count:       int = 0
    low_count:          int = 0
    total_event_count:  int = 0
    overall_risk_level: SeverityLevel = SeverityLevel.LOW

    # 재무 요약 (Decision Agent 연동용)
    latest_debt_ratio:      Optional[float] = None
    latest_op_margin:       Optional[float] = None
    is_net_income_negative: bool            = False

    processed_at:      date           = Field(default_factory=date.today)
    processing_errors: list[str]      = Field(default_factory=list)
