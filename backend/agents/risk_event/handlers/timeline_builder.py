"""R-005 | 타임라인 생성 핸들러

심각도 분류된 이벤트를 날짜순으로 정렬하고
같은 날짜끼리 묶어 TimelineEntry 목록으로 반환한다.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from ..models import SeverityClassifiedEvent, TimelineEntry


def build_timeline(
    classified_events: list[SeverityClassifiedEvent],
) -> list[TimelineEntry]:
    """날짜별 타임라인을 생성한다.

    Args:
        classified_events: 심각도 분류된 이벤트 목록

    Returns:
        날짜 내림차순(최신 우선) TimelineEntry 목록
    """
    buckets: dict[date, list[SeverityClassifiedEvent]] = defaultdict(list)

    for ev in classified_events:
        buckets[ev.event.detected_at].append(ev)

    # 각 날짜 버킷 내에서 심각도 내림차순 정렬
    _severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    timeline = [
        TimelineEntry(
            date=d,
            events=sorted(evs, key=lambda e: _severity_order.get(e.severity.value, 9)),
        )
        for d, evs in buckets.items()
    ]

    # 날짜 내림차순 (최신 이벤트 먼저)
    return sorted(timeline, key=lambda t: t.date, reverse=True)
