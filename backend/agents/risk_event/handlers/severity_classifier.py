"""R-004 | 심각도 분류 핸들러

탐지된 RiskEvent에 Critical / High / Medium / Low 등급을 부여한다.

분류 기준:
  - CRITICAL : 파산·회생·자본잠식·감사의견 거절
  - HIGH     : 부도 키워드·법적 리스크·대규모 차입·적자 전환
  - MEDIUM   : 부정 뉴스·공시 이상·부채비율 급증·영업이익 급감
  - LOW      : 일반 부정 키워드·매출 감소
"""

from __future__ import annotations

from ..models import (
    EventType, RiskEvent, SeverityClassifiedEvent, SeverityLevel,
)

# ─── 이벤트 타입별 기본 심각도 ────────────────────────────────────────────────

_BASE_SEVERITY: dict[EventType, SeverityLevel] = {
    EventType.LEGAL_RISK:         SeverityLevel.CRITICAL,
    EventType.DISCLOSURE_ANOMALY: SeverityLevel.HIGH,
    EventType.FINANCIAL_ANOMALY:  SeverityLevel.HIGH,
    EventType.NEGATIVE_SENTIMENT: SeverityLevel.MEDIUM,
    EventType.NEGATIVE_KEYWORD:   SeverityLevel.MEDIUM,
}

# 제목 키워드로 심각도 상향 조정
_CRITICAL_TITLE_KEYWORDS = ["파산", "회생", "자본잠식", "감사의견 거절", "법정관리"]
_HIGH_TITLE_KEYWORDS     = ["부도", "경매", "가압류", "적자 전환", "횡령", "배임"]

# 심각도 → 점수 매핑
_SEVERITY_SCORE: dict[SeverityLevel, int] = {
    SeverityLevel.CRITICAL: 90,
    SeverityLevel.HIGH:     70,
    SeverityLevel.MEDIUM:   50,
    SeverityLevel.LOW:      25,
}


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def classify_severity(event: RiskEvent) -> SeverityClassifiedEvent:
    """단일 RiskEvent에 심각도를 부여한다."""
    severity = _BASE_SEVERITY.get(event.event_type, SeverityLevel.LOW)

    # 제목 키워드 기반 상향 조정
    title_lower = event.title
    if any(kw in title_lower for kw in _CRITICAL_TITLE_KEYWORDS):
        severity = SeverityLevel.CRITICAL
    elif any(kw in title_lower for kw in _HIGH_TITLE_KEYWORDS):
        if severity == SeverityLevel.MEDIUM or severity == SeverityLevel.LOW:
            severity = SeverityLevel.HIGH

    score = _SEVERITY_SCORE[severity]
    rationale = _build_rationale(event, severity)

    return SeverityClassifiedEvent(
        event=event,
        severity=severity,
        score=score,
        rationale=rationale,
    )


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _build_rationale(event: RiskEvent, severity: SeverityLevel) -> str:
    label_map = {
        SeverityLevel.CRITICAL: "즉각적인 채무불이행 또는 법적 절차 개시 위험",
        SeverityLevel.HIGH:     "재무 건전성 또는 경영 안정성에 심각한 영향 가능",
        SeverityLevel.MEDIUM:   "리스크 신호 감지, 지속 모니터링 필요",
        SeverityLevel.LOW:      "경미한 부정 신호, 단독으로 중대한 위험 아님",
    }
    return f"[{event.event_type.value}] {label_map[severity]}"
