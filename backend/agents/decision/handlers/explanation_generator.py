"""D-004 | 판단 근거 자연어 설명 핸들러

OpenAI API를 호출해 신용등급·승인 결정의 근거를
심사 담당자가 이해할 수 있는 자연어로 설명한다.

변경 사항:
  - 프롬프트에 CRITICAL 상세 원인 블록 추가
  - 프롬프트에 HIGH / MEDIUM 상세 원인 블록 추가
  - sLLM 대응 프롬프트 튜닝: 구체적 작성 규칙 추가
  - sLLM 품질 보완: LLM이 카운트만 반환 시 상세 원인 자동 주입 (신규)
"""

from __future__ import annotations

import logging

from backend.agents.decision.models import (
    DecisionExplanation,
    DecisionResult,
    GradeCalculationResult,
    LimitRecommendationResult,
)
from backend.common.api_client import (
    call_openai,
    get_client,
    get_decision_model_name,
    parse_json_response,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
당신은 기업 신용 심사 전문가입니다.
주어진 심사 데이터를 바탕으로 심사 담당자에게 전달할 설명을 작성하세요.

작성 규칙:
- summary: 기업명, 신용등급, 결정을 포함한 2~3문장 요약. 구체적인 리스크 원인을 1개 이상 언급할 것.
- key_risk_factors: 아래 "상세 원인" 항목을 참고해 구체적인 리스크 요인을 2~4개 작성. 단순히 "HIGH 이벤트 N건"처럼 카운트만 쓰지 말 것. 예시: "영업이익이 전년 대비 58% 급감", "매출이 2년 연속 감소 추세"
- key_positive_factors: 재무 요약에서 긍정적인 지표(낮은 부채비율, 흑자 유지, 낮은 차입금 등)를 2개 이상 추출할 것. 긍정 지표가 없으면 빈 배열.
- recommendation: 심사 담당자를 위한 구체적인 모니터링 권고 1~2문장.

반드시 아래 JSON 형식으로만 응답하세요. JSON 외 다른 텍스트는 출력하지 마세요.
{
  "summary": "전체 심사 결과 2~3문장 요약 (구체적 리스크 언급 포함)",
  "key_risk_factors": ["구체적 리스크 요인 1", "구체적 리스크 요인 2"],
  "key_positive_factors": ["긍정 요인 1", "긍정 요인 2"],
  "recommendation": "심사 담당자를 위한 구체적 권고 1~2문장"
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
    model_name = get_decision_model_name()

    try:
        async with get_client() as client:
            raw = await call_openai(
                client=client,
                messages=[{"role": "user", "content": prompt}],
                system=_SYSTEM_PROMPT,
                model=model_name,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
        parsed = parse_json_response(raw)
        if not isinstance(parsed, dict):
            raise ValueError("응답이 dict 형식이 아닙니다.")

        # sLLM 품질 보완: LLM이 카운트만 반환했으면 상세 원인으로 자동 교체
        key_risks = parsed.get("key_risk_factors", [])
        key_risks = _enrich_risk_factors(key_risks, context)

        return DecisionExplanation(
            summary=parsed.get("summary", ""),
            key_risk_factors=key_risks,
            key_positive_factors=parsed.get("key_positive_factors", []),
            recommendation=parsed.get("recommendation", ""),
        )

    except Exception as exc:
        logger.error("[%s] 설명 생성 실패: %s", company_name, exc)
        return _fallback_explanation(company_name, grade_result, decision, reasons)


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _enrich_risk_factors(
    key_risks: list[str],
    context: dict,
) -> list[str]:
    logger.info("ENRICH_CALLED key_risks=%s", key_risks) 
    """LLM이 카운트만 반환했을 때 상세 원인으로 자동 교체한다.

    sLLM 계열 모델은 instruction following 능력이 낮아
    "HIGH 리스크 이벤트 N건 탐지" 같은 카운트만 반환하는 경우가 있다.
    이 경우 high_reasons / medium_reasons에서 구체적 원인을 직접 추출해
    key_risk_factors를 보강한다.
    """
    # 카운트만 있는지 판별 — 모든 항목이 "건 탐지" 또는 "이벤트"를 포함하면 카운트 전용으로 판단
    is_count_only = bool(key_risks) and all(
        ("탐지" in r) or ("이벤트" in r) or ("건" in r)
        for r in key_risks
    )
    if not is_count_only:
        return key_risks  # LLM이 구체적으로 잘 썼으면 그대로 사용

    logger.info("sLLM 품질 보완: key_risk_factors 카운트 전용 감지 → 상세 원인으로 교체")

    high_reasons = context.get("high_reasons") or []
    medium_reasons = context.get("medium_reasons") or []
    critical_reasons = context.get("critical_reasons") or []

    # 우선순위: CRITICAL → HIGH → MEDIUM, 각 원인에서 핵심 문장만 추출
    enriched = []
    for r in (critical_reasons + high_reasons + medium_reasons[:2]):
        # "(근거: ...)" 부분 제거하고 핵심 원인만 추출
        core = r.split(" (근거:")[0].strip()
        # "[제목] 설명" 형태에서 설명만 추출
        if "] " in core:
            core = core.split("] ", 1)[1].strip()
        if core:
            enriched.append(core)

    # 보강 결과가 없으면 원본 유지
    return enriched if enriched else key_risks


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
    ]

    # CRITICAL 상세 원인
    critical_reasons = context.get("critical_reasons") or []
    if critical_reasons:
        lines.append("  CRITICAL 상세 원인 (key_risk_factors에 반드시 반영할 것):")
        lines.extend(f"    · {r}" for r in critical_reasons)

    # HIGH 상세 원인
    high_reasons = context.get("high_reasons") or []
    if high_reasons:
        lines.append("  HIGH 상세 원인 (key_risk_factors에 반드시 반영할 것):")
        lines.extend(f"    · {r}" for r in high_reasons)

    # MEDIUM 상세 원인
    medium_reasons = context.get("medium_reasons") or []
    if medium_reasons:
        lines.append("  MEDIUM 상세 원인 (key_risk_factors에 참고할 것):")
        lines.extend(f"    · {r}" for r in medium_reasons)

    lines += [
        "",
        "재무 요약 (긍정 지표는 key_positive_factors에 반영할 것):",
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
    )


def _fmt(amount: int | None) -> str:
    if amount is None:
        return "N/A"
    if abs(amount) >= 100_000_000:
        return f"{amount / 100_000_000:.0f}억원"
    return f"{amount:,.0f}원"
