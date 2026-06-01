"""R-006 | 법적 리스크 탐지 핸들러

법원 경매·파산·회생 공고 데이터에서 법적 리스크를 탐지한다.
"""

from __future__ import annotations

from datetime import date

from ..models import (
    EventSource,
    EventType,
    LegalRiskResult,
    RiskEvent,
)

# ─── 법적 리스크 키워드 ───────────────────────────────────────────────────────

_LEGAL_PATTERNS: list[tuple[str, list[str]]] = [
    ("파산",   ["파산선고", "파산 신청", "파산 결정"]),
    ("회생",   ["회생 신청", "회생 결정", "법정관리"]),
    ("경매",   ["경매 개시", "임의경매", "강제경매"]),
    ("가압류", ["가압류 결정", "채권 가압류", "부동산 가압류"]),
]


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def detect_legal_risks(
    company_name: str,
    court_data: list[dict],
) -> LegalRiskResult:
    """법원 공고 데이터에서 법적 리스크를 탐지한다.

    Args:
        company_name: 기업명
        court_data:   법원 공고 목록 (title, content, announced_at, url 포함)

    Returns:
        LegalRiskResult
    """
    legal_risks: list[RiskEvent] = []

    for item in court_data:
        text = f"{item.get('title', '')} {item.get('content', '')}"
        detected_at = _parse_date(item.get("announced_at"))

        for category, keywords in _LEGAL_PATTERNS:
            for kw in keywords:
                if kw in text:
                    legal_risks.append(RiskEvent(
                        event_type=EventType.LEGAL_RISK,
                        source=EventSource.COURT,
                        title=f"법적 리스크: {category}",
                        description=f"'{kw}' 관련 법원 공고가 감지되었습니다. ({item.get('title', '')})",
                        detected_at=detected_at,
                        url=item.get("url"),
                    ))
                    break

    return LegalRiskResult(
        company_name=company_name,
        legal_risks=legal_risks,
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
