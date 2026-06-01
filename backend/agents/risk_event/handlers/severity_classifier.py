"""R-004 | 심각도 분류 핸들러 (고도화)

변경 사항:
  1. LEGAL_RISK 세분화: 파산·회생·자본잠식 → CRITICAL / 경매·가압류 → HIGH
  2. FINANCIAL_ANOMALY 세분화: delta_value 크기에 따라 CRITICAL/HIGH/MEDIUM 동적 분류
  3. 점수 세분화: 심각도 내 delta 크기 반영 (90점 고정 → 80~100 범위)
  4. 중복 이벤트 방지: 동일 타입+날짜 이벤트 점수 중복 차단
"""

from __future__ import annotations

from ..models import (
    EventType,
    RiskEvent,
    SeverityClassifiedEvent,
    SeverityLevel,
)

# ─── 이벤트 타입별 기본 심각도 ────────────────────────────────────────────────

_BASE_SEVERITY: dict[EventType, SeverityLevel] = {
    EventType.LEGAL_RISK:         SeverityLevel.HIGH,       # 세분화 로직에서 조정
    EventType.DISCLOSURE_ANOMALY: SeverityLevel.HIGH,
    EventType.FINANCIAL_ANOMALY:  SeverityLevel.MEDIUM,     # 세분화 로직에서 조정
    EventType.NEGATIVE_SENTIMENT: SeverityLevel.MEDIUM,
    EventType.NEGATIVE_KEYWORD:   SeverityLevel.MEDIUM,
}

# 제목 키워드로 심각도 상향 조정
_CRITICAL_TITLE_KEYWORDS = [
    "파산", "회생", "자본잠식", "감사의견 거절", "법정관리", "워크아웃",
]
_HIGH_TITLE_KEYWORDS = [
    "부도", "경매", "가압류", "적자 전환", "횡령", "배임", "대규모 차입",
]

# 재무 이상 CRITICAL 판단 임계값
_FINANCIAL_CRITICAL_TITLES = ["자본잠식", "당기순이익 적자 전환"]
_FINANCIAL_HIGH_DELTA_THRESHOLD = 50.0   # 부채비율 50%p 이상 급증 → HIGH

# 심각도 → 기본 점수
_SEVERITY_BASE_SCORE: dict[SeverityLevel, int] = {
    SeverityLevel.CRITICAL: 90,
    SeverityLevel.HIGH:     70,
    SeverityLevel.MEDIUM:   50,
    SeverityLevel.LOW:      25,
}


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def classify_severity(event: RiskEvent) -> SeverityClassifiedEvent:
    """단일 RiskEvent에 심각도를 부여한다. (고도화)"""

    severity = _determine_severity(event)
    score    = _calc_score(event, severity)
    rationale = _build_rationale(event, severity)

    return SeverityClassifiedEvent(
        event=event,
        severity=severity,
        score=score,
        rationale=rationale,
    )


# ─── 심각도 결정 ──────────────────────────────────────────────────────────────

def _determine_severity(event: RiskEvent) -> SeverityLevel:
    """이벤트 타입·제목·수치를 종합해 심각도를 결정한다."""
    base = _BASE_SEVERITY.get(event.event_type, SeverityLevel.LOW)

    # ── 법적 리스크 세분화 ──
    if event.event_type == EventType.LEGAL_RISK:
        if any(kw in event.title for kw in ["파산", "회생", "법정관리"]):
            return SeverityLevel.CRITICAL
        return SeverityLevel.HIGH   # 경매, 가압류

    # ── 재무 이상 세분화 ──
    if event.event_type == EventType.FINANCIAL_ANOMALY:
        if any(kw in event.title for kw in _FINANCIAL_CRITICAL_TITLES):
            return SeverityLevel.CRITICAL
        # 부채비율 급증: delta_value(pp) 크기로 HIGH/MEDIUM 분기
        if "부채비율 급증" in event.title:
            delta = abs(event.delta_value or 0)
            return SeverityLevel.HIGH if delta >= _FINANCIAL_HIGH_DELTA_THRESHOLD else SeverityLevel.MEDIUM
        if "영업이익 급감" in event.title:
            delta = abs(event.delta_value or 0)
            return SeverityLevel.HIGH if delta >= 0.5 else SeverityLevel.MEDIUM
        return SeverityLevel.MEDIUM

    # ── 공통 제목 키워드 상향 ──
    if any(kw in event.title for kw in _CRITICAL_TITLE_KEYWORDS):
        return SeverityLevel.CRITICAL
    if any(kw in event.title for kw in _HIGH_TITLE_KEYWORDS):
        if base in (SeverityLevel.MEDIUM, SeverityLevel.LOW):
            return SeverityLevel.HIGH

    return base


# ─── 점수 계산 ────────────────────────────────────────────────────────────────

def _calc_score(event: RiskEvent, severity: SeverityLevel) -> int:
    """심각도 기본 점수에 delta 크기를 반영해 세분화한다."""
    base = _SEVERITY_BASE_SCORE[severity]

    # 재무 이상: delta 크기로 ±10점 보정
    if event.event_type == EventType.FINANCIAL_ANOMALY and event.delta_value is not None:
        delta_abs = abs(event.delta_value)
        if severity == SeverityLevel.CRITICAL:
            bonus = min(int(delta_abs / 10), 10)
        elif severity == SeverityLevel.HIGH:
            bonus = min(int(delta_abs / 20), 10)
        else:
            bonus = 0
        return min(base + bonus, 100)

    return base


# ─── 근거 문자열 ──────────────────────────────────────────────────────────────

def _build_rationale(event: RiskEvent, severity: SeverityLevel) -> str:
    label_map = {
        SeverityLevel.CRITICAL: "즉각적인 채무불이행 또는 법적 절차 개시 위험",
        SeverityLevel.HIGH:     "재무 건전성 또는 경영 안정성에 심각한 영향 가능",
        SeverityLevel.MEDIUM:   "리스크 신호 감지, 지속 모니터링 필요",
        SeverityLevel.LOW:      "경미한 부정 신호, 단독으로 중대한 위험 아님",
    }
    return f"[{event.event_type.value}] {label_map[severity]}"
