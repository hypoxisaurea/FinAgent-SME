"""R-003 | 공시 이상 탐지 핸들러

DART 공시에서 대규모 차입, 담보 제공, 최대주주 변경,
감사의견 거절 등 이상 신호를 탐지한다.
"""

from __future__ import annotations

from datetime import date

from ..models import (
    DisclosureAnomalyResult, EventSource, EventType, RiskEvent,
)

# ─── 이상 공시 패턴 ───────────────────────────────────────────────────────────

_ANOMALY_PATTERNS: list[tuple[str, list[str]]] = [
    ("대규모 차입",       ["단기차입금", "장기차입금", "사채 발행", "대출 약정"]),
    ("담보 제공",         ["담보 제공", "담보설정", "근저당"]),
    ("최대주주 변경",     ["최대주주 변경", "대주주 변경", "경영권 이전"]),
    ("감사의견 거절",     ["감사의견 거절", "의견 거절", "한정 의견", "부적정 의견"]),
    ("소송·분쟁",         ["소송 제기", "중재 신청", "손해배상", "가압류"]),
    ("영업 중단·축소",    ["영업 중단", "사업 중단", "공장 폐쇄", "구조조정"]),
]


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def detect_disclosure_anomalies(
    company_name: str,
    corp_code: str,
    disclosure_data: list[dict],
) -> DisclosureAnomalyResult:
    """공시 목록에서 이상 신호를 탐지한다.

    Args:
        company_name:    기업명
        corp_code:       DART 고유번호
        disclosure_data: 공시 목록 (title, content, disclosed_at, url 포함)

    Returns:
        DisclosureAnomalyResult
    """
    anomalies: list[RiskEvent] = []

    for item in disclosure_data:
        text = f"{item.get('title', '')} {item.get('content', '')}"
        detected_at = _parse_date(item.get("disclosed_at"))

        for category, keywords in _ANOMALY_PATTERNS:
            for kw in keywords:
                if kw in text:
                    anomalies.append(RiskEvent(
                        event_type=EventType.DISCLOSURE_ANOMALY,
                        source=EventSource.DISCLOSURE,
                        title=f"공시 이상: {category}",
                        description=f"'{kw}' 관련 공시가 감지되었습니다. ({item.get('title', '')})",
                        detected_at=detected_at,
                        url=item.get("url"),
                    ))
                    break  # 같은 카테고리 중복 방지

    return DisclosureAnomalyResult(
        company_name=company_name,
        corp_code=corp_code,
        anomalies=anomalies,
        analyzed_at=date.today(),
    )


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.today()
