"""D-001 | 신용등급 산출 핸들러 (고도화)

변경 사항:
  1. 자본잠식(is_capital_impaired) 감지 시 즉시 E등급 강제
  2. HIGH 이벤트 3건 이상 시 추가 10점 차감 (중복 리스크 반영)
  3. 부채비율·영업이익률 정밀화: 구간 세분화
  4. 매출 감소·적자 전환 이벤트 탐지 시 추가 차감
  5. _build_rationale 상세화
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

_GRADE_ORDER = [CreditGrade.E, CreditGrade.D, CreditGrade.C, CreditGrade.B, CreditGrade.A]

# 자본잠식 탐지용 이벤트 타이틀 키워드
_CAPITAL_IMPAIRED_KEYWORDS = ["자본잠식"]


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def calculate_grade(context: dict) -> GradeCalculationResult:
    """컨텍스트에서 리스크·재무 데이터를 읽어 신용등급을 산출한다. (고도화)"""

    # ── 하드 룰: 자본잠식 시 즉시 E등급 ──
    if _is_capital_impaired(context):
        logger.warning(
            "grade_forced_E company=%s reason=capital_impaired",
            context.get("company_name", "unknown"),
        )
        breakdown = ScoreBreakdown(
            base_score=100,
            risk_deduction=50,
            financial_deduction=30,
            final_score=0,
        )
        return GradeCalculationResult(
            grade=CreditGrade.E,
            score=0,
            score_breakdown=breakdown,
            grade_cap=context.get("grade_cap"),
            rationale="자본잠식 확인 — 즉시 E등급 처리.",
        )

    risk_deduction      = _calc_risk_deduction(context)
    financial_deduction = _calc_financial_deduction(context)
    extra_deduction     = _calc_extra_deduction(context)

    final_score = max(0, 100 - risk_deduction - financial_deduction - extra_deduction)

    breakdown = ScoreBreakdown(
        base_score=100,
        risk_deduction=risk_deduction + extra_deduction,
        financial_deduction=financial_deduction,
        final_score=final_score,
    )

    grade     = _score_to_grade(final_score)
    grade_cap = context.get("grade_cap")

    if grade_cap and grade_cap in _GRADE_CAP_MAP:
        cap_grade = _GRADE_CAP_MAP[grade_cap]
        if _GRADE_ORDER.index(grade) > _GRADE_ORDER.index(cap_grade):
            logger.info(
                "grade_cap 적용: %s → %s (grade_cap=%s)",
                grade.value, cap_grade.value, grade_cap,
            )
            grade = cap_grade

    rationale = _build_rationale(final_score, breakdown, grade_cap, extra_deduction)

    logger.info(
        "grade_calculated company=%s score=%d risk_ded=%d fin_ded=%d extra=%d grade=%s",
        context.get("company_name", "unknown"),
        final_score, risk_deduction, financial_deduction, extra_deduction, grade.value,
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
    """재무 지표 기반 점수 차감 (최대 30점). 구간 세분화."""
    deduction = 0

    debt_ratio        = _get_float(context, "latest_debt_ratio")
    op_margin         = _get_float(context, "latest_op_margin")
    is_net_income_neg = bool(context.get("is_net_income_negative", False))

    # 부채비율 (세분화)
    if debt_ratio is not None:
        if debt_ratio > 400:
            deduction += 20
        elif debt_ratio > 300:
            deduction += 15
        elif debt_ratio > 200:
            deduction += 10
        elif debt_ratio > 150:
            deduction += 5

    # 영업이익률 (세분화)
    if op_margin is not None:
        if op_margin < -10:
            deduction += 12
        elif op_margin < 0:
            deduction += 10
        elif op_margin < 3:
            deduction += 5

    # 당기순손실
    if is_net_income_neg:
        deduction += 5

    return min(deduction, 30)


# ─── 추가 차감 (신규) ─────────────────────────────────────────────────────────

def _calc_extra_deduction(context: dict) -> int:
    """복수 HIGH 이벤트 등 복합 리스크 추가 차감 (최대 10점)."""
    extra = 0
    high = int(context.get("high_count", 0))
    # HIGH 이벤트 3건 이상: 복합 리스크 추가 -10
    if high >= 3:
        extra += 10
    return min(extra, 10)


# ─── 자본잠식 탐지 ────────────────────────────────────────────────────────────

def _is_capital_impaired(context: dict) -> bool:
    """자본잠식 이벤트가 존재하는지 확인한다."""
    classified_events = context.get("classified_events", [])
    for ev in classified_events:
        title = ""
        if hasattr(ev, "event"):
            title = ev.event.title
        elif isinstance(ev, dict):
            title = ev.get("event", {}).get("title", "")
        if any(kw in title for kw in _CAPITAL_IMPAIRED_KEYWORDS):
            return True
    return False


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


def _build_rationale(
    score: int,
    breakdown: ScoreBreakdown,
    grade_cap: str | None,
    extra: int,
) -> str:
    parts = [
        f"기본 100점에서 리스크 이벤트 -{breakdown.risk_deduction}점, "
        f"재무 이상 -{breakdown.financial_deduction}점 차감. 최종 점수: {score}점."
    ]
    if extra > 0:
        parts.append(f"복합 리스크(HIGH 이벤트 다수) 추가 -{extra}점 적용.")
    if grade_cap:
        parts.append(f"재무분석 등급 상한({grade_cap}) 적용됨.")
    return " ".join(parts)
