"""R-002 | 뉴스 감성 분석 핸들러

기사마다 API를 호출하던 방식을 개선해
모든 뉴스를 한 번의 API 호출로 배치 처리한다.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.utils.api_client import call_claude, get_client, parse_json_response
from ..models import (
    EventSource, EventType, RiskEvent,
    SentimentAnalysisResult, SentimentLabel,
)

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 200   # 기사당 본문 최대 길이 (비용 절감)

_SYSTEM_PROMPT = """
당신은 금융 뉴스 감성 분석 전문가입니다.
뉴스 목록을 읽고 각 기사에 대해 아래 JSON 배열 형식으로만 응답하세요.
[
  {"index": 0, "sentiment": "positive" | "neutral" | "negative", "reason": "판단 근거 한 문장"},
  {"index": 1, ...}
]
JSON 외 다른 텍스트는 출력하지 마세요.
"""


async def analyze_sentiment(
    company_name: str,
    news_data: list[dict],
) -> SentimentAnalysisResult:
    """뉴스 목록을 한 번의 API 호출로 배치 감성 분석한다.

    Args:
        company_name: 기업명
        news_data:    뉴스 목록 (title, content, published_at, url 포함)

    Returns:
        SentimentAnalysisResult
    """
    counts = {SentimentLabel.POSITIVE: 0, SentimentLabel.NEUTRAL: 0, SentimentLabel.NEGATIVE: 0}
    events: list[RiskEvent] = []

    if not news_data:
        return SentimentAnalysisResult(
            company_name=company_name,
            news_items=news_data,
            negative_count=0,
            neutral_count=0,
            positive_count=0,
            overall_sentiment=SentimentLabel.NEUTRAL,
            detected_events=[],
        )

    # 모든 기사를 하나의 프롬프트로 묶기
    prompt = _build_batch_prompt(company_name, news_data)

    results: list[dict] = []
    try:
        async with get_client() as client:
            raw = await call_claude(
                client=client,
                messages=[{"role": "user", "content": prompt}],
                system=_SYSTEM_PROMPT,
                max_tokens=1500,
            )
        results = parse_json_response(raw)
        if not isinstance(results, list):
            raise ValueError("응답이 배열 형식이 아닙니다.")

    except Exception as e:
        logger.error("[%s] 감성 분석 실패: %s", company_name, e)
        # 실패 시 전체 중립 처리
        results = [{"index": i, "sentiment": "neutral", "reason": "분석 실패"} for i in range(len(news_data))]

    # 결과 처리
    for item_result in results:
        idx = item_result.get("index", 0)
        if idx >= len(news_data):
            continue

        news_item = news_data[idx]
        try:
            label = SentimentLabel(item_result.get("sentiment", "neutral"))
        except ValueError:
            label = SentimentLabel.NEUTRAL

        counts[label] += 1

        if label == SentimentLabel.NEGATIVE:
            events.append(RiskEvent(
                event_type=EventType.NEGATIVE_SENTIMENT,
                source=EventSource.NEWS,
                title=f"부정 뉴스: {news_item.get('title', '')[:40]}",
                description=item_result.get("reason", ""),
                detected_at=_parse_date(news_item.get("published_at")),
                url=news_item.get("url"),
            ))

    # 전체 감성 판단
    total = sum(counts.values()) or 1
    if counts[SentimentLabel.NEGATIVE] / total > 0.5:
        overall = SentimentLabel.NEGATIVE
    elif counts[SentimentLabel.POSITIVE] / total > 0.5:
        overall = SentimentLabel.POSITIVE
    else:
        overall = SentimentLabel.NEUTRAL

    return SentimentAnalysisResult(
        company_name=company_name,
        news_items=news_data,
        negative_count=counts[SentimentLabel.NEGATIVE],
        neutral_count=counts[SentimentLabel.NEUTRAL],
        positive_count=counts[SentimentLabel.POSITIVE],
        overall_sentiment=overall,
        detected_events=events,
    )


def _build_batch_prompt(company_name: str, news_data: list[dict]) -> str:
    """모든 뉴스를 하나의 프롬프트로 묶는다."""
    lines = [f"기업명: {company_name}\n분석 대상 뉴스 {len(news_data)}건:\n"]
    for i, item in enumerate(news_data):
        title   = item.get("title", "")
        content = item.get("content", "")[:MAX_CONTENT_CHARS]
        lines.append(f"[{i}] 제목: {title}\n    본문: {content}")
    return "\n".join(lines)


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.today()
