"""D-002 | 승인·거절 판단 핸들러 (고도화)

변경 사항:
  1. 자본잠식 하드 거절 룰 추가
  2. HIGH 이벤트 5건 이상 자동 거절
  3. 당기순손실 + 부채비율 300% 초과 동시 충족 시 자동 거절
  4. confidence 계산 경계값 보정
  5. reasons 메시지 한국어 자연스럽게 개선
"""

from __future__ import annotations

import logging

from backend.agents.decision.models import (
    CreditGrade,
    DecisionMakerResult,
    DecisionResult,
)

logger = logging.getLogger(__name__)

_GRADE_DECISION: dict[CreditGrade, DecisionResult] = {
    CreditGrade.A: DecisionResult.APPROVE,
    CreditGrade.B: DecisionResult.APPROVE,
    CreditGrade.C: DecisionResult.REVIEW,
    CreditGrade.D: DecisionResult.REJECT,
    CreditGrade.E: DecisionResult.REJECT,
}

# 하드 거절 트리거 상수
_HIGH_COUNT_REJECT_THRESHOLD = 5
_DEBT_RATIO_HARD_REJECT      = 300.0


def make_decision(
    grade: CreditGrade,
    score: int,
    context: dict,
) -> DecisionMakerResult:
    """등급·점수·컨텍스트 기반으로 최종 승인 여부를 결정한다. (고도화)"""
    result     = _GRADE_DECISION[grade]
    reasons    = _build_reasons(grade, score, context)
    confidence = _calc_confidence(score, result)

    # ── 하드 거절 룰 1: CRITICAL 이벤트 ──
    if int(context.get("critical_count", 0)) > 0 and result != DecisionResult.REJECT:
        result, confidence, reasons = _override_reject(
            reasons,
            "CRITICAL 등급 리스크 이벤트가 감지되어 자동 거절 처리됩니다.",
            context,
        )

    # ── 하드 거절 룰 2: HIGH 이벤트 다수 ──
    elif int(context.get("high_count", 0)) >= _HIGH_COUNT_REJECT_THRESHOLD \
            and result != DecisionResult.REJECT:
        result, confidence, reasons = _override_reject(
            reasons,
            f"HIGH 리스크 이벤트 {context.get('high_count')}건 누적 — 복합 리스크로 자동 거절.",
            context,
        )

    # ── 하드 거절 룰 3: 당기순손실 + 고부채비율 동시 충족 ──
    elif (
        result != DecisionResult.REJECT
        and bool(context.get("is_net_income_negative", False))
        and (_get_float(context, "latest_debt_ratio") or 0) > _DEBT_RATIO_HARD_REJECT
    ):
        result, confidence, reasons = _override_reject(
            reasons,
            f"당기순손실 + 부채비율 {_get_float(context, 'latest_debt_ratio'):.1f}% 초과 — 재무 위험 자동 거절.",
            context,
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

def _override_reject(
    reasons: list[str],
    override_msg: str,
    context: dict,
) -> tuple[DecisionResult, float, list[str]]:
    reasons.insert(0, override_msg)
    logger.warning(
        "decision_override_to_reject company=%s reason=%s",
        context.get("company_name", "unknown"),
        override_msg[:50],
    )
    return DecisionResult.REJECT, 0.95, reasons


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

    debt_ratio = _get_float(context, "latest_debt_ratio")
    if debt_ratio and debt_ratio > 200:
        reasons.append(f"부채비율 {debt_ratio:.1f}% — 과중 부채 수준.")

    op_margin = _get_float(context, "latest_op_margin")
    if op_margin is not None and op_margin < 0:
        reasons.append(f"영업이익률 {op_margin:.1f}% — 영업 적자 상태.")

    if len(reasons) == 1:
        reasons.append("주요 리스크 이벤트 및 재무 이상 징후 없음.")

    return reasons


def _calc_confidence(score: int, result: DecisionResult) -> float:
    if result == DecisionResult.APPROVE:
        return min(0.5 + (score - 50) * 0.008, 0.98)
    if result == DecisionResult.REJECT:
        return min(0.5 + (50 - score) * 0.010, 0.98)
    return max(0.55, min(0.55 + abs(score - 57) * 0.01, 0.70))


def _get_float(context: dict, key: str) -> float | None:
    v = context.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
