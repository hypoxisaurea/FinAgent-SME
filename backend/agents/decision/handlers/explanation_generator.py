"""D-004 | 판단 근거 자연어 설명 핸들러

OpenAI API를 호출해 신용등급·승인 결정의 근거를
심사 담당자가 이해할 수 있는 자연어로 설명한다.
"""

from __future__ import annotations

import logging

from backend.agents.decision.models import (
    DecisionExplanation,
    DecisionResult,
    GradeCalculationResult,
    LimitRecommendationResult,
)
from backend.utils.api_client import call_openai, get_client, parse_json_response

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
당신은 기업 신용 심사 전문가입니다.
주어진 심사 데이터를 바탕으로 심사 담당자에게 전달할 설명을 작성하세요.
반드시 아래 JSON 형식으로만 응답하세요. JSON 외 다른 텍스트는 출력하지 마세요.
{
  "summary": "전체 심사 결과 2~3문장 요약",
  "key_risk_factors": ["리스크 요인 1", "리스크 요인 2"],
  "key_positive_factors": ["긍정 요인 1", "긍정 요인 2"],
  "recommendation": "심사 담당자를 위한 최종 권고 1~2문장"
}
"""


async def generate_explanation(
    company_name: str,
    grade_result: GradeCalculationResult,
    decision: DecisionResult,
    limit_result: LimitRecommendationResult,
    reasons: list[str],
    context: dict,
) -> DecisionExplanation:
    """OpenAI API로 판단 근거 자연어 설명을 생성한다.

    Args:
        company_name:  기업명
        grade_result:  신용등급 산출 결과
        decision:      승인·거절 결정
        limit_result:  한도 추천 결과
        reasons:       주요 판단 이유 목록
        context:       Orchestrator 누적 컨텍스트

    Returns:
        DecisionExplanation (API 실패 시 fallback 반환)
    """
    prompt = _build_prompt(
        company_name,
        grade_result,
        decision,
        limit_result,
        reasons,
        context,
    )

    try:
        async with get_client() as client:
            raw = await call_openai(
                client=client,
                messages=[{"role": "user", "content": prompt}],
                system=_SYSTEM_PROMPT,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
        parsed = parse_json_response(raw)
        if not isinstance(parsed, dict):
            raise ValueError("응답이 dict 형식이 아닙니다.")

        return DecisionExplanation(
            summary=parsed.get("summary", ""),
            key_risk_factors=parsed.get("key_risk_factors", []),
            key_positive_factors=parsed.get("key_positive_factors", []),
            recommendation=parsed.get("recommendation", ""),
            fallback_used=False,
        )

    except Exception as exc:
        logger.error("[%s] 설명 생성 실패: %s", company_name, exc)
        return _fallback_explanation(company_name, grade_result, decision, reasons)


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _build_prompt(
    company_name: str,
    grade_result: GradeCalculationResult,
    decision: DecisionResult,
    limit_result: LimitRecommendationResult,
    reasons: list[str],
    context: dict,
) -> str:
    decision_label = {
        DecisionResult.APPROVE: "승인",
        DecisionResult.REVIEW:  "조건부 검토",
        DecisionResult.REJECT:  "거절",
    }[decision]

    limit_str = (
        f"{limit_result.limit_range} (권장: {_fmt(limit_result.recommended_limit)})"
        if limit_result.recommended_limit
        else "해당 없음"
    )

    lines = [
        f"기업명: {company_name}",
        f"신용등급: {grade_result.grade.value} ({grade_result.score}점)",
        f"결정: {decision_label}",
        f"추천 한도: {limit_str}",
        "",
        "주요 판단 근거:",
        *[f"  - {r}" for r in reasons],
        "",
        "리스크 이벤트 요약:",
        f"  CRITICAL: {context.get('critical_count', 0)}건",
        f"  HIGH:     {context.get('high_count', 0)}건",
        f"  MEDIUM:   {context.get('medium_count', 0)}건",
        "",
        "재무 요약:",
        f"  부채비율:   {context.get('latest_debt_ratio', 'N/A')}%",
        f"  영업이익률: {context.get('latest_op_margin', 'N/A')}%",
        f"  당기순손실: {'있음' if context.get('is_net_income_negative') else '없음'}",
    ]
    return "\n".join(lines)


def _fallback_explanation(
    company_name: str,
    grade_result: GradeCalculationResult,
    decision: DecisionResult,
    reasons: list[str],
) -> DecisionExplanation:
    """API 실패 시 규칙 기반 fallback 설명을 반환한다."""
    decision_label = {
        DecisionResult.APPROVE: "승인",
        DecisionResult.REVIEW:  "조건부 검토",
        DecisionResult.REJECT:  "거절",
    }[decision]

    return DecisionExplanation(
        summary=(
            f"{company_name}의 신용등급은 "
            f"{grade_result.grade.value}({grade_result.score}점)으로 "
            f"최종 {decision_label} 결정이 내려졌습니다."
        ),
        key_risk_factors=[
            r
            for r in reasons
            if any(w in r for w in ["리스크", "적자", "부채", "거절", "손실"])
        ],
        key_positive_factors=[r for r in reasons if "없음" in r or "양호" in r],
        recommendation=grade_result.rationale,
        fallback_used=True,
    )


def _fmt(amount: int | None) -> str:
    if amount is None:
        return "N/A"
    if abs(amount) >= 100_000_000:
        return f"{amount / 100_000_000:.0f}억원"
    return f"{amount:,.0f}원"
