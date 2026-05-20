"""Decision Agent Pydantic 모델

신용등급 산출, 승인/거절 판단, 한도 추천, 설명 결과를 정의한다.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─── 열거형 ──────────────────────────────────────────────────────────────────

class CreditGrade(str, Enum):
    A = "A"   # 80-100점: 최우량
    B = "B"   # 65-79점:  우량
    C = "C"   # 50-64점:  보통 (조건부)
    D = "D"   # 35-49점:  주의
    E = "E"   # 0-34점:   불량


class DecisionResult(str, Enum):
    APPROVE = "approve"   # 승인
    REVIEW  = "review"    # 보류/조건부 검토
    REJECT  = "reject"    # 거절


# ─── 핸들러별 출력 ────────────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    """점수 구성 상세"""
    base_score:          int = 100
    risk_deduction:      int = 0
    financial_deduction: int = 0
    final_score:         int = 100


class GradeCalculationResult(BaseModel):
    """D-001 신용등급 산출 결과"""
    grade:           CreditGrade
    score:           int                   # 0-100
    score_breakdown: ScoreBreakdown
    grade_cap:       Optional[str] = None  # financial_analyst grade_cap 반영 시
    rationale:       str


class DecisionMakerResult(BaseModel):
    """D-002 승인·거절 판단 결과"""
    result:     DecisionResult
    confidence: float          # 0.0 ~ 1.0
    reasons:    list[str]


class LimitRecommendationResult(BaseModel):
    """D-003 한도 추천 결과"""
    recommended_limit: Optional[int] = None   # 원 단위
    limit_range:       Optional[str] = None   # 예: "5억 ~ 10억"
    limit_basis:       str = ""


class DecisionExplanation(BaseModel):
    """D-004 판단 근거 자연어 설명"""
    summary:               str
    key_risk_factors:      list[str]
    key_positive_factors:  list[str]
    recommendation:        str


# ─── 최종 출력 ────────────────────────────────────────────────────────────────

class DecisionOutput(BaseModel):
    """Decision Agent 최종 출력 스키마"""
    company_name: str
    corp_code:    str

    # D-001 신용등급
    grade:       CreditGrade
    grade_score: int

    # D-002 승인·거절
    decision:   DecisionResult
    confidence: float
    reasons:    list[str] = Field(default_factory=list)

    # D-003 한도
    recommended_limit: Optional[int] = None
    limit_range:       Optional[str] = None
    limit_basis:       str = ""

    # D-004 설명
    explanation: Optional[DecisionExplanation] = None

    # 상세 내역
    grade_detail: GradeCalculationResult

    processed_at:      date      = Field(default_factory=date.today)
    processing_errors: list[str] = Field(default_factory=list)