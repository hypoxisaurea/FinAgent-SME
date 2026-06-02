"""D-003 | 한도 추천 핸들러

신용등급과 재무 데이터(매출, 총자산)를 기반으로
적정 대출 한도를 추천한다.

한도 산정 기준:
  A등급: min(총자산 × 30%, 연매출 × 50%), 상한 50억
  B등급: min(총자산 × 20%, 연매출 × 30%), 상한 30억
  C등급: min(총자산 × 10%, 연매출 × 20%), 상한 10억 (조건부)
  D, E: 한도 없음 (거절)
"""

from __future__ import annotations

import logging

from backend.agents.decision.models import (
    CreditGrade,
    DecisionResult,
    LimitRecommendationResult,
)

logger = logging.getLogger(__name__)

# 등급별 한도 파라미터
_LIMIT_PARAMS: dict[CreditGrade, dict] = {
    CreditGrade.A: {"asset_ratio": 0.30, "revenue_ratio": 0.50, "cap": 5_000_000_000},
    CreditGrade.B: {"asset_ratio": 0.20, "revenue_ratio": 0.30, "cap": 3_000_000_000},
    CreditGrade.C: {"asset_ratio": 0.10, "revenue_ratio": 0.20, "cap": 1_000_000_000},
    CreditGrade.D: {},
    CreditGrade.E: {},
}

# 기본 한도 (재무 데이터 없을 때)
_DEFAULT_LIMITS: dict[CreditGrade, int] = {
    CreditGrade.A: 2_000_000_000,   # 20억
    CreditGrade.B: 1_000_000_000,   # 10억
    CreditGrade.C:   300_000_000,   # 3억
}


def recommend_limit(
    grade: CreditGrade,
    decision: DecisionResult,
    context: dict,
) -> LimitRecommendationResult:
    """등급과 재무 데이터 기반 대출 한도를 추천한다.

    Args:
        grade:    신용등급 (A~E)
        decision: 승인/보류/거절 결정
        context:  Orchestrator 누적 컨텍스트

    Returns:
        LimitRecommendationResult
    """
    if decision == DecisionResult.REJECT:
        logger.info(
            "limit_skipped company=%s reason=rejected",
            context.get("company_name", "unknown"),
        )
        return LimitRecommendationResult(
            recommended_limit=0,
            limit_range=None,
            limit_basis="거절 결정으로 한도 없음.",
        )

    params = _LIMIT_PARAMS.get(grade, {})
    if not params:
        return LimitRecommendationResult(
            recommended_limit=0,
            limit_basis="해당 등급은 한도 산정 대상이 아닙니다.",
        )

    total_assets = _get_amount(context, "total_assets") or _get_amount(context, "total_assets_statement")
    revenue      = _get_amount(context, "revenue") or _get_amount(context, "avg_revenue_last_3y")

    if total_assets and revenue:
        limit_by_assets  = int(total_assets * params["asset_ratio"])
        limit_by_revenue = int(revenue      * params["revenue_ratio"])
        recommended      = min(limit_by_assets, limit_by_revenue, params["cap"])
        lower_bound      = int(recommended * 0.7)
        basis            = (
            f"총자산({_fmt(total_assets)}) × {params['asset_ratio']*100:.0f}% = {_fmt(limit_by_assets)}, "
            f"연매출({_fmt(revenue)}) × {params['revenue_ratio']*100:.0f}% = {_fmt(limit_by_revenue)} 중 낮은 값 적용."
        )
    elif total_assets:
        recommended = min(int(total_assets * params["asset_ratio"]), params["cap"])
        lower_bound = int(recommended * 0.7)
        basis       = f"총자산({_fmt(total_assets)}) × {params['asset_ratio']*100:.0f}% 기준 산정."
    elif revenue:
        recommended = min(int(revenue * params["revenue_ratio"]), params["cap"])
        lower_bound = int(recommended * 0.7)
        basis       = f"연매출({_fmt(revenue)}) × {params['revenue_ratio']*100:.0f}% 기준 산정."
    else:
        recommended = _DEFAULT_LIMITS.get(grade, 0)
        lower_bound = int(recommended * 0.7)
        basis       = "재무 데이터 미확인 — 등급별 보수적 기본값 적용."

    limit_range = f"{_fmt(lower_bound)} ~ {_fmt(recommended)}"

    logger.info(
        "limit_recommended company=%s grade=%s limit=%s",
        context.get("company_name", "unknown"),
        grade.value,
        _fmt(recommended),
    )

    return LimitRecommendationResult(
        recommended_limit=recommended,
        limit_range=limit_range,
        limit_basis=basis,
    )


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _get_amount(context: dict, key: str) -> float | None:
    v = context.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _fmt(amount: float) -> str:
    if abs(amount) >= 1_000_000_000_000:
        return f"{amount / 1_000_000_000_000:.1f}조원"
    if abs(amount) >= 100_000_000:
        return f"{amount / 100_000_000:.0f}억원"
    if abs(amount) >= 10_000_000:
        return f"{amount / 10_000_000:.0f}천만원"
    return f"{amount:,.0f}원"
