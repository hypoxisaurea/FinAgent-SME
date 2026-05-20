"""D-001 | 신용등급 산출 핸들러

Risk Event Agent 결과와 재무 데이터를 기반으로
0-100점 점수를 산출하고 A~E 등급을 부여한다.

점수 구조:
  Base 100점에서 리스크/재무 이상 지표에 따라 차감
  - 리스크 이벤트 차감:   최대 50점
  - 재무 이상 차감:       최대 30점
  - 최종 점수 → 등급 변환
"""

from __future__ import annotations

import logging

from ..models import CreditGrade, GradeCalculationResult, ScoreBreakdown

logger = logging.getLogger(__name__)

# ─── 등급 기준 ────────────────────────────────────────────────────────────────

_GRADE_THRESHOLDS: list[tuple[int, CreditGrade]] = [
    (80, CreditGrade.A),
    (65, CreditGrade.B),
    (50, CreditGrade.C),
    (35, CreditGrade.D),
    (0,  CreditGrade.E),
]

# grade_cap (financial_analyst 산출) → 강제 등급 하한
_GRADE_CAP_MAP: dict[str, CreditGrade] = {
    "AAA": CreditGrade.A,
    "AA":  CreditGrade.A,
    "A":   CreditGrade.A,
    "BBB": CreditGrade.B,
    "BB+": CreditGrade.C,
    "BB":  CreditGrade.C,
    "B+":  CreditGrade.D,
    "B":   CreditGrade.D,
    "CCC": CreditGrade.E,
}

# 등급 순서 (낮을수록 불량)
_GRADE_ORDER = [CreditGrade.E, CreditGrade.D, CreditGrade.C, CreditGrade.B, CreditGrade.A]


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def calculate_grade(context: dict) -> GradeCalculationResult:
    """컨텍스트에서 리스크·재무 데이터를 읽어 신용등급을 산출한다.

    Args:
        context: Orchestrator가 누적한 전체 컨텍스트
                 (RiskEventAgent 출력 + CollectorAgent 출력 포함)

    Returns:
        GradeCalculationResult
    """
    risk_deduction      = _calc_risk_deduction(context)
    financial_deduction = _calc_financial_deduction(context)

    final_score = max(0, 100 - risk_deduction - financial_deduction)

    breakdown = ScoreBreakdown(
        base_score=100,
        risk_deduction=risk_deduction,
        financial_deduction=financial_deduction,
        final_score=final_score,
    )

    grade    = _score_to_grade(final_score)
    grade_cap = context.get("grade_cap")

    # financial_analyst grade_cap 적용 (더 엄격한 쪽 우선)
    if grade_cap and grade_cap in _GRADE_CAP_MAP:
        cap_grade = _GRADE_CAP_MAP[grade_cap]
        if _GRADE_ORDER.index(grade) > _GRADE_ORDER.index(cap_grade):
            logger.info(
                "grade_cap 적용: %s → %s (grade_cap=%s)",
                grade.value, cap_grade.value, grade_cap,
            )
            grade = cap_grade

    rationale = _build_rationale(final_score, breakdown, grade_cap)

    logger.info(
        "grade_calculated company=%s score=%d risk_ded=%d fin_ded=%d grade=%s",
        context.get("company_name", "unknown"),
        final_score,
        risk_deduction,
        financial_deduction,
        grade.value,
    )

    return GradeCalculationResult(
        grade=grade,
        score=final_score,
        score_breakdown=breakdown,
        grade_cap=grade_cap,
        rationale=rationale,
    )


# ─── 리스크 이벤트 차감 ───────────────────────────────────────────────────────

def _calc_risk_deduction(context: dict) -> int:
    """Risk Event Agent 결과 기반 점수 차감 (최대 50점)."""
    critical = int(context.get("critical_count", 0))
    high     = int(context.get("high_count",     0))
    medium   = int(context.get("medium_count",   0))
    low      = int(context.get("low_count",      0))

    deduction = (
        min(critical, 3) * 20
        + min(high, 3)   * 10
        + min(medium, 5) *  5
        + min(low, 5)    *  1
    )
    return min(deduction, 50)


# ─── 재무 이상 차감 ───────────────────────────────────────────────────────────

def _calc_financial_deduction(context: dict) -> int:
    """재무 지표 기반 점수 차감 (최대 30점).

    우선순위:
      1. RiskEventAgent의 latest_debt_ratio / latest_op_margin / is_net_income_negative
      2. 위 값 없으면 financial_analyst 결과에서 탐색
    """
    deduction = 0

    debt_ratio           = _get_float(context, "latest_debt_ratio")
    op_margin            = _get_float(context, "latest_op_margin")
    is_net_income_neg    = bool(context.get("is_net_income_negative", False))

    # 부채비율
    if debt_ratio is not None:
        if debt_ratio > 300:
            deduction += 15
        elif debt_ratio > 200:
            deduction += 10
        elif debt_ratio > 150:
            deduction += 5

    # 영업이익률
    if op_margin is not None:
        if op_margin < 0:
            deduction += 10
        elif op_margin < 5:
            deduction += 5

    # 당기순손실
    if is_net_income_neg:
        deduction += 5

    return min(deduction, 30)


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _score_to_grade(score: int) -> CreditGrade:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return CreditGrade.E


def _get_float(context: dict, key: str) -> float | None:
    v = context.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _build_rationale(score: int, breakdown: ScoreBreakdown, grade_cap: str | None) -> str:
    parts = [
        f"기본 100점에서 리스크 이벤트 -{breakdown.risk_deduction}점, "
        f"재무 이상 -{breakdown.financial_deduction}점 차감. 최종 점수: {score}점."
    ]
    if grade_cap:
        parts.append(f"재무분석 등급 상한({grade_cap}) 적용됨.")
    return " ".join(parts)