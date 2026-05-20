"""D-002 | 승인·거절 판단 핸들러

신용등급과 리스크 요인을 기반으로
approve / review / reject 결정을 산출한다.

판단 기준:
  A, B  → approve  (신뢰도: 점수가 기준에서 멀수록 높음)
  C     → review   (조건부 검토)
  D, E  → reject
"""

from __future__ import annotations

import logging

from ..models import CreditGrade, DecisionMakerResult, DecisionResult

logger = logging.getLogger(__name__)

# 등급 → 기본 결정
_GRADE_DECISION: dict[CreditGrade, DecisionResult] = {
    CreditGrade.A: DecisionResult.APPROVE,
    CreditGrade.B: DecisionResult.APPROVE,
    CreditGrade.C: DecisionResult.REVIEW,
    CreditGrade.D: DecisionResult.REJECT,
    CreditGrade.E: DecisionResult.REJECT,
}

# 점수 구간별 confidence 계산 기준점
_CONFIDENCE_ANCHORS: list[tuple[int, float]] = [
    (90, 0.95),
    (80, 0.85),
    (65, 0.75),
    (50, 0.60),
    (35, 0.55),
    (0,  0.90),  # 명확한 거절도 신뢰도 높음
]


def make_decision(
    grade: CreditGrade,
    score: int,
    context: dict,
) -> DecisionMakerResult:
    """등급·점수·컨텍스트 기반으로 최종 승인 여부를 결정한다.

    Args:
        grade:   신용등급 (A~E)
        score:   신용점수 (0~100)
        context: Orchestrator 누적 컨텍스트

    Returns:
        DecisionMakerResult
    """
    result     = _GRADE_DECISION[grade]
    reasons    = _build_reasons(grade, score, context)
    confidence = _calc_confidence(score, result)

    # CRITICAL 이벤트 존재 시 자동 거절
    if int(context.get("critical_count", 0)) > 0 and result != DecisionResult.REJECT:
        result     = DecisionResult.REJECT
        confidence = 0.95
        reasons.insert(0, "CRITICAL 등급 리스크 이벤트가 감지되어 자동 거절 처리됩니다.")
        logger.warning(
            "decision_override_to_reject company=%s reason=critical_event",
            context.get("company_name", "unknown"),
        )

    logger.info(
        "decision_made company=%s grade=%s score=%d result=%s confidence=%.2f",
        context.get("company_name", "unknown"),
        grade.value, score, result.value, confidence,
    )

    return DecisionMakerResult(
        result=result,
        confidence=confidence,
        reasons=reasons,
    )


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _build_reasons(grade: CreditGrade, score: int, context: dict) -> list[str]:
    reasons: list[str] = []

    reasons.append(f"신용등급 {grade.value} (점수: {score}점)으로 평가되었습니다.")

    critical = int(context.get("critical_count", 0))
    high     = int(context.get("high_count",     0))
    medium   = int(context.get("medium_count",   0))

    if critical > 0:
        reasons.append(f"CRITICAL 리스크 이벤트 {critical}건 탐지.")
    if high > 0:
        reasons.append(f"HIGH 리스크 이벤트 {high}건 탐지.")
    if medium > 0:
        reasons.append(f"MEDIUM 리스크 이벤트 {medium}건 탐지.")

    if context.get("is_net_income_negative"):
        reasons.append("최근 연도 당기순손실 기록.")

    debt_ratio = context.get("latest_debt_ratio")
    if debt_ratio and float(debt_ratio) > 200:
        reasons.append(f"부채비율 {float(debt_ratio):.1f}% — 과중 부채 수준.")

    op_margin = context.get("latest_op_margin")
    if op_margin is not None and float(op_margin) < 0:
        reasons.append(f"영업이익률 {float(op_margin):.1f}% — 영업 적자 상태.")

    if not reasons[1:]:
        reasons.append("주요 리스크 이벤트 및 재무 이상 징후 없음.")

    return reasons


def _calc_confidence(score: int, result: DecisionResult) -> float:
    """점수 기반 신뢰도 계산.

    경계값(50, 65, 80)에서 멀수록 신뢰도가 높아진다.
    """
    if result == DecisionResult.APPROVE:
        # 80점 이상 구간: 점수가 높을수록 신뢰도 UP
        return min(0.5 + (score - 50) * 0.008, 0.98)
    if result == DecisionResult.REJECT:
        # 낮은 점수일수록 신뢰도 UP
        return min(0.5 + (50 - score) * 0.010, 0.98)
    # REVIEW: 중간 구간 → 0.55~0.70
    return 0.55 + abs(score - 57) * 0.01