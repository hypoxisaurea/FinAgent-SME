"""R-001 | 부정 키워드 탐지 핸들러

뉴스 및 공시 텍스트에서 부도·소송·횡령·사기·경매 등
위험 키워드를 탐지하고 RiskEvent 목록으로 반환한다.
"""

from __future__ import annotations

from datetime import date

from backend.agents.risk_event.models import (
    EventSource,
    EventType,
    KeywordDetectionResult,
    RiskEvent,
)

# ─── 키워드 사전 ──────────────────────────────────────────────────────────────

RISK_KEYWORDS: dict[str, list[str]] = {
    "부도·파산":   ["부도", "파산", "회생", "법정관리", "워크아웃"],
    "소송·법적":   ["소송", "고소", "피소", "기소", "재판", "가압류", "압류"],
    "횡령·비리":   ["횡령", "배임", "사기", "뇌물", "비리", "불법"],
    "경영 리스크": ["대표이사 교체", "최대주주 변경", "경영권 분쟁", "감사의견 거절"],
    "경매·담보":   ["경매", "공매", "담보 제공", "채무불이행"],
}


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def detect_keywords(
    company_name: str,
    news_data: list[dict],
    disclosure_data: list[dict],
) -> KeywordDetectionResult:
    """뉴스와 공시에서 부정 키워드를 탐지한다.

    Args:
        company_name:    기업명
        news_data:       뉴스 목록 (title, content, published_at, url 포함)
        disclosure_data: 공시 목록 (title, content, disclosed_at 포함)

    Returns:
        KeywordDetectionResult
    """
    events: list[RiskEvent] = []

    # 뉴스 탐지
    for item in news_data:
        text = f"{item.get('title', '')} {item.get('content', '')}"
        _scan_text(
            text=text,
            source=EventSource.NEWS,
            detected_at=_parse_date(item.get("published_at")),
            url=item.get("url"),
            events=events,
        )

    # 공시 탐지
    for item in disclosure_data:
        text = f"{item.get('title', '')} {item.get('content', '')}"
        _scan_text(
            text=text,
            source=EventSource.DISCLOSURE,
            detected_at=_parse_date(item.get("disclosed_at")),
            url=item.get("url"),
            events=events,
        )

    return KeywordDetectionResult(
        company_name=company_name,
        detected_events=events,
        analyzed_at=date.today(),
    )


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _scan_text(
    text: str,
    source: EventSource,
    detected_at: date,
    url: str | None,
    events: list[RiskEvent],
) -> None:
    for category, keywords in RISK_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                events.append(RiskEvent(
                    event_type=EventType.NEGATIVE_KEYWORD,
                    source=source,
                    title=f"부정 키워드 탐지: {kw}",
                    description=f"[{category}] '{kw}' 키워드가 감지되었습니다.",
                    detected_at=detected_at,
                    url=url,
                ))
                break  # 같은 카테고리 중복 방지


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.today()
