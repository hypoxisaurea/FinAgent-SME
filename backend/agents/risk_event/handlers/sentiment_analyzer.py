"""R-002 | 뉴스 감성 분석 핸들러

LLM(Claude API)을 사용해 뉴스 기사를 긍정·부정·중립으로 분류하고
부정 뉴스에서 RiskEvent를 생성한다.
"""

from __future__ import annotations

import json
import os
from datetime import date

import httpx

from ..models import (
    EventSource, EventType, RiskEvent,
    SentimentAnalysisResult, SentimentLabel,
)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = """
당신은 금융 뉴스 감성 분석 전문가입니다.
뉴스 제목과 본문을 읽고 아래 JSON 형식으로만 응답하세요.
{
  "sentiment": "positive" | "neutral" | "negative",
  "reason": "판단 근거 한 문장"
}
"""


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

async def analyze_sentiment(
    company_name: str,
    news_data: list[dict],
) -> SentimentAnalysisResult:
    """뉴스 목록의 감성을 LLM으로 분류한다.

    Args:
        company_name: 기업명
        news_data:    뉴스 목록 (title, content, published_at, url 포함)

    Returns:
        SentimentAnalysisResult
    """
    counts = {SentimentLabel.POSITIVE: 0, SentimentLabel.NEUTRAL: 0, SentimentLabel.NEGATIVE: 0}
    events: list[RiskEvent] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for item in news_data:
            label, reason = await _classify_single(client, item)
            counts[label] += 1

            if label == SentimentLabel.NEGATIVE:
                events.append(RiskEvent(
                    event_type=EventType.NEGATIVE_SENTIMENT,
                    source=EventSource.NEWS,
                    title=f"부정 뉴스: {item.get('title', '')[:40]}",
                    description=reason,
                    detected_at=_parse_date(item.get("published_at")),
                    url=item.get("url"),
                ))

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


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

async def _classify_single(
    client: httpx.AsyncClient,
    item: dict,
) -> tuple[SentimentLabel, str]:
    """단일 뉴스 기사의 감성을 분류한다."""
    text = f"제목: {item.get('title', '')}\n본문: {item.get('content', '')[:500]}"

    try:
        resp = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 200,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": text}],
            },
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"]
        parsed = json.loads(raw)
        label = SentimentLabel(parsed.get("sentiment", "neutral"))
        reason = parsed.get("reason", "")
        return label, reason

    except Exception:
        return SentimentLabel.NEUTRAL, "분석 실패"


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.today()
