from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


RISK_LOOKBACK_DAYS = 90


def build_report_view_model(
    result: dict[str, Any],
    context: dict[str, Any],
    report_payload: dict[str, Any],
    decision_step: dict[str, Any] | None,
) -> dict[str, Any]:
    explanation = context.get("explanation") or {} if isinstance(context, dict) else {}
    company_profile = context.get("company_profile") or {} if isinstance(context, dict) else {}
    risk_filters = context.get("risk_filters") or {} if isinstance(context, dict) else {}
    altman_z = context.get("altman_z") or {} if isinstance(context, dict) else {}
    financial_ratios = context.get("financial_ratios") or {} if isinstance(context, dict) else {}

    decision = report_payload.get("decision") or context.get("decision") or "-"
    credit_grade = report_payload.get("credit_grade") or context.get("credit_grade") or "-"
    confidence = report_payload.get("confidence")
    if confidence is None:
        confidence = context.get("decision_confidence")
    recommended_limit = report_payload.get("recommended_limit")
    if recommended_limit is None:
        recommended_limit = context.get("recommended_limit")

    recent_risk_events = _extract_recent_risk_events(context)
    financial_flags = _as_list(context.get("financial_flags"))
    decision_reasons = _as_list(context.get("decision_reasons"))
    news_result = context.get("news_result", {}) if isinstance(context, dict) else {}
    risk_event_result = context.get("risk_event_result", {}) if isinstance(context, dict) else {}
    if not isinstance(risk_event_result, dict) or not risk_event_result:
        risk_event_result = _build_risk_event_result_fallback(context)
    api_warnings = _extract_api_warnings(news_result)

    return {
        "overview": {
            "company_name": report_payload.get("company_name") or context.get("company_name") or "대상 기업",
            "corp_name": report_payload.get("corp_name") or context.get("corp_name") or "-",
            "corp_code": report_payload.get("corp_code") or context.get("corp_code") or "-",
            "stock_code": company_profile.get("stock_code") or "-",
            "generated_at": report_payload.get("generated_at") or "-",
            "workflow_status": result.get("status", "unknown"),
            "decision": decision,
            "credit_grade": credit_grade,
            "confidence": _format_confidence(confidence),
            "recommended_limit": _format_currency(recommended_limit),
            "overall_risk_level": _format_risk_level(context.get("overall_risk_level")),
            "key_reasons": decision_reasons[:3],
            "api_warnings": api_warnings,
        },
        "sections": {
            "company": {
                "title": "1. 기업 개요",
                "rows": [
                    ("법인명", report_payload.get("corp_name") or context.get("corp_name") or "-"),
                    ("법인코드", report_payload.get("corp_code") or context.get("corp_code") or "-"),
                    ("종목코드", company_profile.get("stock_code") or "-"),
                    ("대표자", company_profile.get("ceo_name") or "-"),
                    ("설립일", company_profile.get("established_date") or "-"),
                    ("주소", company_profile.get("address") or "-"),
                    ("홈페이지", company_profile.get("homepage_url") or "-"),
                    ("업종", context.get("ksic_code") or company_profile.get("industry_code") or "-"),
                    ("결산월", company_profile.get("settlement_month") or "-"),
                ],
            },
            "financial_health": {
                "title": "2. 재무 건전성 분석",
                "metrics": [
                    ("매출액", _format_currency(context.get("revenue"))),
                    ("영업이익", _format_currency(context.get("operating_income"))),
                    ("당기순이익", _format_currency(context.get("net_income"))),
                    ("총자산", _format_currency(context.get("total_assets"))),
                    ("부채비율", _format_percent(financial_ratios.get("debt_ratio"))),
                    ("유동비율", _format_percent(financial_ratios.get("current_ratio"))),
                    ("영업이익률", _format_percent(financial_ratios.get("op_margin"))),
                    ("이자보상배율", _format_ratio(financial_ratios.get("interest_coverage"))),
                ],
                "interpretation": _build_financial_interpretation(context),
                "credit_impact": _build_financial_credit_impact(context),
                "ratio_groups": _build_financial_ratio_groups(financial_ratios),
            },
            "growth_trend": {
                "title": "3. 성장성 및 추세 분석",
                "recent_trend": _build_recent_trend_summary(context),
                "financial_flags": financial_flags,
                "history_rows": _build_trend_history_rows(context),
                "chart_rows": _build_trend_chart_rows(context),
            },
            "industry_analysis": {
                "title": "4. 산업/업황 분석",
                **_build_industry_analysis_section(context),
            },
            "non_financial_events": {
                "title": "5. 통합 리스크 이벤트 분석",
                **_build_non_financial_event_section(context, risk_event_result),
            },
            "default_risk": {
                "title": "6. 부도위험 및 등급 제한 요인",
                "z_score": _format_decimal(altman_z.get("z_prime")),
                "zone": altman_z.get("zone") or "-",
                "grade_cap": context.get("grade_cap") or risk_filters.get("grade_cap") or "-",
                "triggered_filters": _as_list(risk_filters.get("triggered_filters")),
                "filter_details": _flatten_filter_details(risk_filters.get("filter_detail")),
            },
            "decision_rationale": {
                "title": "7. 종합 신용판단 근거",
                "summary": explanation.get("summary") or report_payload.get("summary") or "-",
                "connected_reason": _build_connected_reason(context, explanation),
                "reasons": _group_decision_reasons(decision_reasons),
                "positive_factors": _build_decision_event_factors(
                    context,
                    explanation.get("key_positive_factors"),
                ),
                "risk_factors": _build_decision_risk_factors(context, explanation),
            },
            "monitoring": {
                "title": "8. 권고안 및 모니터링 포인트",
                "recommendation": report_payload.get("recommendation")
                or explanation.get("recommendation")
                or "-",
                "decision": _format_decision(decision),
                "recommended_limit": _format_currency(recommended_limit),
                "monitoring_points": _build_monitoring_points(
                    financial_flags=financial_flags,
                    recent_risk_events=recent_risk_events,
                    triggered_filters=_as_list(risk_filters.get("triggered_filters")),
                ),
                "recent_risk_events": recent_risk_events,
            },
            "decision_detail": {
                "credit_score": _pick_value(decision_step, context, "credit_score"),
                "limit_range": _pick_value(decision_step, context, "limit_range"),
                "limit_basis": _pick_value(decision_step, context, "limit_basis"),
                "processing_errors": _as_list(context.get("processing_errors")),
                "risk_counts": {
                    "critical": context.get("critical_count", 0),
                    "high": context.get("high_count", 0),
                    "medium": context.get("medium_count", 0),
                    "low": context.get("low_count", 0),
                },
            },
        },
    }


def _pick_value(step: dict[str, Any] | None, context: dict[str, Any], key: str) -> Any:
    if isinstance(step, dict) and step.get(key) is not None:
        return step.get(key)
    return context.get(key)


def _group_decision_reasons(items: list[str]) -> list[str]:
    if not items:
        return []

    grouped: list[str] = []
    index = 0
    while index < len(items):
        current = str(items[index]).strip()
        if not current:
            index += 1
            continue

        if "리스크 이벤트" in current:
            block_lines = [current]
            lookahead = index + 1
            while lookahead < len(items):
                candidate = str(items[lookahead]).strip()
                if not candidate:
                    lookahead += 1
                    continue
                if candidate.startswith("- "):
                    block_lines.append(candidate)
                    lookahead += 1
                    continue
                break
            grouped.append("\n".join(block_lines))
            index = lookahead
            continue

        grouped.append(current)
        index += 1

    return grouped


def _extract_recent_risk_events(context: dict[str, Any]) -> list[str]:
    timeline = context.get("timeline")
    if not isinstance(timeline, list):
        return []

    cutoff = date.today() - timedelta(days=RISK_LOOKBACK_DAYS)
    recent_events: list[tuple[int, date, str]] = []

    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        entry_date = _parse_date(entry.get("date"))
        events = entry.get("events")
        if not isinstance(events, list):
            continue
        for event_wrapper in events:
            severity_raw = _normalize_severity(_object_get(event_wrapper, "severity"))
            include_without_date = entry_date is None and severity_raw in {"critical", "high"}
            if entry_date is not None and entry_date < cutoff:
                continue
            if entry_date is None and not include_without_date:
                continue
            event = _object_get(event_wrapper, "event", {})
            severity = _format_risk_level(severity_raw)
            title = str(_object_get(event, "title") or _object_get(event, "description") or "-")
            date_label = entry_date.isoformat() if entry_date is not None else "무일자"
            sort_date = entry_date or date.min
            dated_priority = 1 if entry_date is not None else 0
            recent_events.append((dated_priority, sort_date, f"{date_label} | {severity} | {title}"))

    recent_events.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [text for _, _, text in recent_events[:5]]


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _flatten_filter_details(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    items = []
    for key, detail in value.items():
        items.append(f"{key}: {detail}")
    return items


def _extract_api_warnings(news_result: dict[str, Any]) -> list[str]:
    if not isinstance(news_result, dict):
        return []
    warnings: list[str] = []
    for reason in news_result.get("summary_error_reasons", []) or []:
        text = str(reason).strip()
        if not text:
            continue
        warnings.append(f"뉴스 요약 API 상태: {text}")
    return warnings


def _build_risk_event_result_fallback(context: dict[str, Any]) -> dict[str, Any]:
    sentiment_result = context.get("sentiment_result")
    if not isinstance(sentiment_result, dict):
        sentiment_result = {}

    return {
        "sentiment_result": sentiment_result,
        "classified_events": context.get("classified_events", []),
        "timeline": context.get("timeline", []),
        "overall_risk_level": context.get("overall_risk_level"),
        "critical_count": context.get("critical_count", 0),
        "high_count": context.get("high_count", 0),
        "medium_count": context.get("medium_count", 0),
        "low_count": context.get("low_count", 0),
        "total_event_count": context.get("total_event_count", 0),
    }


def _build_financial_ratio_groups(financial_ratios: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(financial_ratios, dict):
        financial_ratios = {}

    return [
        {
            "title": "안정성",
            "items": [
                ("부채비율", _format_percent(financial_ratios.get("debt_ratio"))),
                ("유동비율", _format_percent(financial_ratios.get("current_ratio"))),
                ("당좌비율", _format_percent(financial_ratios.get("quick_ratio"))),
                ("차입금의존도", _format_percent(financial_ratios.get("borrow_dep"))),
                ("이자보상배율", _format_ratio(financial_ratios.get("interest_coverage"))),
            ],
        },
        {
            "title": "수익성",
            "items": [
                ("영업이익률", _format_percent(financial_ratios.get("op_margin"))),
                ("ROA", _format_percent(financial_ratios.get("roa"))),
                ("매출원가율", _format_percent(financial_ratios.get("cogs_ratio"))),
            ],
        },
        {
            "title": "활동성",
            "items": [
                ("매출채권회전율", _format_ratio(financial_ratios.get("receivable_turnover"))),
                ("총자산회전율", _format_ratio(financial_ratios.get("asset_turnover"))),
                ("매입채무회전율", _format_ratio(financial_ratios.get("payable_turnover"))),
            ],
        },
        {
            "title": "현금흐름",
            "items": [
                ("OCF/매출액", _format_percent(financial_ratios.get("ocf_to_sales"))),
                ("OCF/순이익", _format_ratio(financial_ratios.get("ocf_to_net_income"))),
                ("FCF", _format_currency(financial_ratios.get("fcf"))),
                ("FCF/매출액", _format_percent(financial_ratios.get("fcf_to_sales"))),
            ],
        },
    ]


def _build_non_financial_event_section(
    context: dict[str, Any],
    risk_event_result: dict[str, Any],
) -> dict[str, Any]:
    all_event_items = _extract_timeline_event_items(
        context,
        risk_event_result=risk_event_result,
        limit=20,
    )
    timeline_events = all_event_items[:5]
    severe_events = [
        item for item in all_event_items if _normalize_severity(item.get("severity_raw")) in {"critical", "high"}
    ]
    repeated_title_count = _count_repeated_titles(timeline_events)
    overall_risk_level = _format_risk_level(context.get("overall_risk_level"))

    sentiment_result = {}
    if isinstance(risk_event_result, dict):
        sentiment_result = risk_event_result.get("sentiment_result", {}) or {}

    overall_sentiment = "-"
    positive_sentiment_count = 0
    positive_event_items: list[dict[str, str]] = []
    if isinstance(sentiment_result, dict):
        overall_sentiment = _format_sentiment(sentiment_result.get("overall_sentiment"))
        positive_sentiment_count = int(sentiment_result.get("positive_count", 0) or 0)
        positive_event_items = _extract_positive_sentiment_items(sentiment_result, limit=5)
    financial_anomaly_items = _extract_financial_anomaly_items(context, risk_event_result, limit=5)

    critical_count = int(context.get("critical_count", 0) or 0)
    high_count = int(context.get("high_count", 0) or 0)
    medium_count = int(context.get("medium_count", 0) or 0)
    total_event_count = int(context.get("total_event_count", 0) or 0)

    if critical_count > 0:
        repayment_impact = "CRITICAL 이벤트가 확인되어 단기 상환능력과 거래 안정성에 직접적인 영향 가능성이 큽니다."
    elif high_count > 0:
        repayment_impact = "HIGH 이벤트가 확인되어 상환 재원 안정성 저하 가능성을 보수적으로 점검할 필요가 있습니다."
    elif medium_count >= 2:
        repayment_impact = "중간 수준 이벤트가 반복되어 감지 이벤트가 상환능력에 간접 영향을 줄 수 있습니다."
    else:
        repayment_impact = "최근 감지 이벤트가 상환능력에 미치는 직접 영향은 제한적으로 보입니다."

    if repeated_title_count > 0:
        repeat_summary = f"동일하거나 유사한 감지 이벤트가 최근 90일 내 {repeated_title_count}건 반복 관측되었습니다."
    else:
        repeat_summary = "최근 90일 기준 반복적으로 누적된 동일 이슈는 제한적입니다."

    visible_event_count = critical_count + high_count + medium_count
    severity_summary = (
        f"최근 90일 이벤트 {visible_event_count}건 중 "
        f"CRITICAL {critical_count}건, HIGH {high_count}건, MEDIUM {medium_count}건으로 집계됩니다."
        if visible_event_count > 0
        else "최근 90일 내 표시할 통합 리스크 이벤트가 없습니다."
    )

    key_event_lines = [
        f"{item['date']} | {item['severity']} | {item['title']} | {item['impact']}"
        for item in severe_events[:3]
    ]
    if not key_event_lines:
        key_event_lines = [
            f"{item['date']} | {item['severity']} | {item['title']} | {item['impact']}"
            for item in timeline_events[:3]
        ]

    timeline_lines = [
        f"{item['date']} | {item['severity']} | {item['title']} | {item['impact']}"
        for item in timeline_events
    ]

    return {
        "overall_risk_level": overall_risk_level,
        "overall_sentiment": overall_sentiment,
        "positive_sentiment_count": positive_sentiment_count,
        "recentness_summary": severity_summary,
        "repeat_summary": repeat_summary,
        "repayment_impact": repayment_impact,
        "critical_high_events": key_event_lines,
        "timeline_lines": timeline_lines,
        "timeline_items": timeline_events,
        "key_event_items": severe_events[:3] if severe_events else timeline_events[:3],
        "positive_event_items": positive_event_items,
        "financial_anomaly_items": financial_anomaly_items,
        "total_event_count": total_event_count,
    }


def _build_industry_analysis_section(context: dict[str, Any]) -> dict[str, Any]:
    industry_summary = context.get("industry_summary")
    if not isinstance(industry_summary, dict):
        industry_summary = {}
    industry_outlook = context.get("industry_outlook")
    if not isinstance(industry_outlook, dict):
        industry_outlook = {}
    business_cycle = context.get("business_cycle")
    if not isinstance(business_cycle, dict):
        business_cycle = {}
    macro_indicators = context.get("macro_indicators")
    if not isinstance(macro_indicators, dict):
        macro_indicators = {}
    peer_comparison = context.get("peer_comparison")
    if not isinstance(peer_comparison, dict):
        peer_comparison = {}

    methodology = industry_outlook.get("industry_methodology")
    if not isinstance(methodology, dict):
        methodology = {}

    return {
        "sector_note": str(industry_summary.get("sector_note") or "업종 특성 데이터가 없습니다."),
        "outlook_score": str(industry_outlook.get("outlook_score") or context.get("outlook_score") or "-"),
        "outlook_note": str(industry_outlook.get("note") or "업황 해석 정보가 없습니다."),
        "business_cycle_phase": str(
            business_cycle.get("phase")
            or business_cycle.get("business_cycle_phase")
            or "-"
        ),
        "macro_note": _build_macro_note(macro_indicators),
        "peer_highlights": _build_peer_highlights(peer_comparison),
        "methodology_summary": str(methodology.get("summary") or "산업 방법론 요약이 없습니다."),
        "methodology_risks": _as_list(methodology.get("key_risk_factors"))[:3],
    }


def _build_macro_note(macro_indicators: dict[str, Any]) -> str:
    for key in ("fx_impact", "note"):
        value = str(macro_indicators.get(key) or "").strip()
        if value:
            return value

    base_rate = macro_indicators.get("base_rate")
    usd_krw = macro_indicators.get("usd_krw")
    rate_trend = str(macro_indicators.get("rate_trend") or "").strip()
    parts: list[str] = []
    if base_rate not in (None, ""):
        parts.append(f"기준금리 {base_rate}")
    if usd_krw not in (None, ""):
        parts.append(f"원달러 환율 {usd_krw}")
    if rate_trend:
        parts.append(f"금리 추세 {rate_trend}")
    return ", ".join(parts) if parts else "거시 영향 해석 정보가 없습니다."


def _build_peer_highlights(peer_comparison: dict[str, Any]) -> list[str]:
    highlights: list[str] = []
    name_map = {
        "op_margin": "영업이익률",
        "debt_ratio": "부채비율",
        "current_ratio": "유동비율",
        "interest_coverage": "이자보상배율",
        "borrow_dep": "차입금의존도",
        "receivable_turnover": "매출채권회전율",
        "asset_turnover": "총자산회전율",
        "sales_growth": "매출액증가율",
    }
    judgment_map = {
        "better": "산업 평균 대비 우위",
        "worse": "산업 평균 대비 열위",
        "in-line": "산업 평균 수준",
    }
    for key, item in peer_comparison.items():
        if not isinstance(item, dict):
            continue
        judgment = str(item.get("judgment") or "").strip()
        if judgment not in judgment_map:
            continue
        label = name_map.get(key, key)
        highlights.append(f"{label}: {judgment_map[judgment]}")
    return highlights[:4]


def _extract_timeline_event_items(
    context: dict[str, Any],
    risk_event_result: dict[str, Any] | None = None,
    limit: int = 5,
) -> list[dict[str, str]]:
    classified_items = _extract_classified_event_items(context, risk_event_result)
    if classified_items:
        return classified_items[:limit]

    timeline = context.get("timeline")
    if not isinstance(timeline, list):
        return []

    cutoff = date.today() - timedelta(days=RISK_LOOKBACK_DAYS)
    items: list[tuple[int, date, dict[str, str]]] = []

    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        entry_date = _parse_date(entry.get("date"))
        events = entry.get("events")
        if not isinstance(events, list):
            continue
        for event_wrapper in events:
            event = _object_get(event_wrapper, "event", {})
            severity_raw = _normalize_severity(_object_get(event_wrapper, "severity"))
            include_without_date = entry_date is None and severity_raw in {"critical", "high"}
            if entry_date is not None and entry_date < cutoff:
                continue
            if entry_date is None and not include_without_date:
                continue
            severity = _format_risk_level(severity_raw)
            title = str(_object_get(event, "title") or _object_get(event, "description") or "-").strip()
            rationale = str(_object_get(event_wrapper, "rationale") or "").strip()
            description = str(_object_get(event, "description") or "").strip()
            impact = rationale or description or "구체 영향 설명 정보가 없습니다."
            display_date = entry_date.isoformat() if entry_date is not None else "무일자"
            sort_date = entry_date or date.min
            dated_priority = 1 if entry_date is not None else 0
            items.append(
                (
                    dated_priority,
                    sort_date,
                    {
                        "date": display_date,
                        "severity_raw": severity_raw,
                        "severity": severity,
                        "event_type": _format_event_type(_object_get(event, "event_type")),
                        "source": _format_event_source(_object_get(event, "source")),
                        "title": title or "-",
                        "impact": impact,
                    },
                )
            )

    items.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [payload for _, _, payload in items[:limit]]


def _extract_classified_event_items(
    context: dict[str, Any],
    risk_event_result: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    source = risk_event_result if isinstance(risk_event_result, dict) and risk_event_result else context
    classified_events = source.get("classified_events")
    if not isinstance(classified_events, list):
        return []

    cutoff = date.today() - timedelta(days=RISK_LOOKBACK_DAYS)
    items: list[tuple[int, date, dict[str, str]]] = []

    for wrapper in classified_events:
        event = _object_get(wrapper, "event")
        if event is None:
            continue
        severity_raw = _normalize_severity(_object_get(wrapper, "severity"))
        detected_at = _parse_date(_object_get(event, "detected_at"))
        include_without_date = detected_at is None and severity_raw in {"critical", "high"}
        if detected_at is not None and detected_at < cutoff:
            continue
        if detected_at is None and not include_without_date:
            continue
        severity = _format_risk_level(severity_raw)
        title = str(_object_get(event, "title") or _object_get(event, "description") or "-").strip() or "-"
        rationale = str(_object_get(wrapper, "rationale") or "").strip()
        description = str(_object_get(event, "description") or "").strip()
        impact = rationale or description or "구체 영향 설명 정보가 없습니다."
        sort_date = detected_at or date.min
        dated_priority = 1 if detected_at is not None else 0
        items.append(
            (
                dated_priority,
                sort_date,
                {
                    "date": detected_at.isoformat() if detected_at is not None else "무일자",
                    "severity_raw": severity_raw,
                    "severity": severity,
                    "event_type": _format_event_type(_object_get(event, "event_type")),
                    "source": _format_event_source(_object_get(event, "source")),
                    "title": title,
                    "impact": impact,
                },
            )
        )

    items.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [payload for _, _, payload in items]


def _extract_positive_sentiment_items(
    sentiment_result: dict[str, Any],
    limit: int = 5,
) -> list[dict[str, str]]:
    article_sentiments = sentiment_result.get("article_sentiments")
    if not isinstance(article_sentiments, list):
        return []

    cutoff = date.today() - timedelta(days=RISK_LOOKBACK_DAYS)
    items: list[tuple[date, dict[str, str]]] = []
    for item in article_sentiments:
        if not isinstance(item, dict):
            continue
        sentiment = str(item.get("sentiment") or "").lower()
        if sentiment != "positive":
            continue
        published_at = _parse_date(item.get("published_at"))
        if published_at is None or published_at < cutoff:
            continue
        title = str(item.get("title") or "-").strip() or "-"
        reason = str(item.get("reason") or "").strip() or "긍정 요인으로 해석된 기사입니다."
        items.append(
            (
                published_at,
                {
                    "date": published_at.isoformat(),
                    "severity_raw": "positive",
                    "severity": "긍정",
                    "event_type": "긍정 뉴스",
                    "source": "뉴스",
                    "title": title,
                    "impact": reason,
                },
            )
        )

    items.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in items[:limit]]


def _extract_financial_anomaly_items(
    context: dict[str, Any],
    risk_event_result: dict[str, Any] | None = None,
    limit: int = 5,
) -> list[dict[str, str]]:
    source = risk_event_result if isinstance(risk_event_result, dict) and risk_event_result else context
    financial_result = source.get("financial_result")
    if financial_result is None:
        financial_result = context.get("financial_result")

    anomalies = _object_get(financial_result, "anomalies", [])
    if not isinstance(anomalies, list):
        return []

    items: list[tuple[date, dict[str, str]]] = []
    for event in anomalies:
        detected_at = _parse_date(_object_get(event, "detected_at"))
        sort_date = detected_at or date.min
        title = str(_object_get(event, "title") or _object_get(event, "description") or "-").strip() or "-"
        impact = str(_object_get(event, "description") or "구체 영향 설명 정보가 없습니다.").strip()
        items.append(
            (
                sort_date,
                {
                    "date": detected_at.isoformat() if detected_at is not None else "무일자",
                    "severity_raw": _infer_financial_anomaly_severity(event),
                    "severity": _format_risk_level(_infer_financial_anomaly_severity(event)),
                    "event_type": "재무 이상 탐지",
                    "source": "재무 데이터",
                    "title": title,
                    "impact": impact,
                },
            )
        )

    items.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in items[:limit]]


def _count_repeated_titles(items: list[dict[str, str]]) -> int:
    counts: dict[str, int] = {}
    for item in items:
        title = item.get("title", "").strip()
        if not title or title == "-":
            continue
        counts[title] = counts.get(title, 0) + 1
    return sum(count - 1 for count in counts.values() if count > 1)


def _format_sentiment(value: Any) -> str:
    return {
        "negative": "부정",
        "neutral": "중립",
        "positive": "긍정",
    }.get(str(value).lower(), str(value or "-"))


def _infer_financial_anomaly_severity(event: Any) -> str:
    title = str(_object_get(event, "title") or "").lower()
    description = str(_object_get(event, "description") or "").lower()
    combined = f"{title} {description}"
    if "급감" in combined or "적자" in combined:
        return "high"
    return "medium"


def _format_event_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "financial_anomaly": "재무 이상 탐지",
        "negative_sentiment": "부정 뉴스",
        "negative_keyword": "부정 키워드",
        "disclosure_anomaly": "공시 이상",
        "legal_risk": "법률 리스크",
    }.get(normalized, str(value or "-"))


def _format_event_source(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "financial_data": "재무 데이터",
        "news": "뉴스",
        "disclosure": "공시",
        "court": "법원",
    }.get(normalized, str(value or "-"))


def _object_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _normalize_severity(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    if "." in text:
        text = text.split(".")[-1]
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    alias_map = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "positive": "positive",
        "negative": "negative",
        "neutral": "neutral",
    }
    return alias_map.get(text, text)


def _build_financial_interpretation(context: dict[str, Any]) -> str:
    ratios = context.get("financial_ratios", {})
    if not isinstance(ratios, dict):
        ratios = {}

    debt_ratio = ratios.get("debt_ratio")
    current_ratio = ratios.get("current_ratio")
    op_margin = ratios.get("op_margin")

    parts = []
    if isinstance(debt_ratio, (int, float)):
        if debt_ratio >= 200:
            parts.append("부채 부담이 높은 수준입니다.")
        elif debt_ratio >= 100:
            parts.append("부채 부담은 관리 가능하나 보수적 관찰이 필요합니다.")
        else:
            parts.append("부채 부담은 상대적으로 안정적인 수준입니다.")
    if isinstance(current_ratio, (int, float)):
        if current_ratio < 100:
            parts.append("단기 유동성은 다소 약한 편입니다.")
        else:
            parts.append("단기 유동성 대응력은 양호한 편입니다.")
    if isinstance(op_margin, (int, float)):
        if op_margin < 0:
            parts.append("영업수익성이 음수로 수익 구조 점검이 필요합니다.")
        elif op_margin < 5:
            parts.append("영업수익성은 낮지만 흑자는 유지 중입니다.")
        else:
            parts.append("영업수익성은 비교적 안정적으로 보입니다.")

    return " ".join(parts) or "재무 해석을 위한 핵심 비율 데이터가 충분하지 않습니다."


def _build_financial_credit_impact(context: dict[str, Any]) -> str:
    grade_cap = context.get("grade_cap")
    overall_risk_level = _format_risk_level(context.get("overall_risk_level"))
    if grade_cap:
        return f"재무 필터에 따라 등급 상한 {grade_cap}가 적용되어 최종 판단 여력을 제약합니다. 비금융 리스크 수준은 {overall_risk_level}입니다."
    return f"재무 지표만으로 강한 등급 제한은 없으나, 최종 신용판단에는 비금융 리스크 수준 {overall_risk_level}가 함께 반영됩니다."


def _build_connected_reason(context: dict[str, Any], explanation: dict[str, Any]) -> str:
    financial_summary = context.get("financial_summary")
    industry_summary = context.get("industry_summary")
    overall_risk_level = _format_risk_level(context.get("overall_risk_level"))
    decision = _format_decision(context.get("decision"))

    financial_phrase = "재무 정보가 제한적입니다"
    if isinstance(financial_summary, str) and financial_summary.strip():
        financial_phrase = financial_summary.strip()
    elif isinstance(context.get("financial_flags"), list) and context["financial_flags"]:
        financial_phrase = "재무 추세상 주의 플래그가 관찰됩니다"

    industry_phrase = ""
    if isinstance(industry_summary, str) and industry_summary.strip():
        candidate = industry_summary.strip()
        if candidate != "산업·거시 판단 정보가 제한적입니다":
            industry_phrase = candidate
        else:
            industry_phrase = "산업 분석 데이터 미확보"

    explanation_summary = ""
    if isinstance(explanation, dict):
        explanation_summary = str(explanation.get("summary") or "").strip()

    sentence_parts = [financial_phrase]
    if industry_phrase:
        sentence_parts.append(f"동시에 {industry_phrase}")
    sentence_parts.append(
        f"비금융 리스크 수준은 {overall_risk_level}로 평가되어 최종적으로 {decision} 판단을 내렸습니다."
    )
    sentence = " ".join(part for part in sentence_parts if part)
    if explanation_summary:
        return f"{sentence} {explanation_summary}"
    return sentence


def _build_monitoring_points(
    financial_flags: list[str],
    recent_risk_events: list[str],
    triggered_filters: list[str],
) -> list[str]:
    points: list[str] = []
    for flag in financial_flags[:2]:
        points.append(f"재무 추세 모니터링: {flag}")
    for event in recent_risk_events[:2]:
        points.append(f"최근 90일 이벤트 재확인: {event}")
    for filter_name in triggered_filters[:2]:
        points.append(f"등급 제한 요인 재점검: {filter_name}")
    if not points:
        points.append("추가 정성 자료와 최근 현금흐름 자료를 받아 재확인하는 것을 권고합니다.")
    return points


def _build_decision_risk_factors(
    context: dict[str, Any],
    explanation: dict[str, Any],
) -> list[str]:
    return _build_decision_event_factors(context, explanation.get("key_risk_factors"))


def _build_decision_event_factors(
    context: dict[str, Any],
    factors: Any,
) -> list[str]:
    base_factors = _as_list(factors)
    if not base_factors:
        return []

    recent_event_items = _extract_timeline_event_items(context, limit=20)
    severity_examples: dict[str, list[str]] = {"critical": [], "high": [], "medium": [], "low": []}
    for item in recent_event_items:
        severity_raw = _normalize_severity(item.get("severity_raw"))
        title = str(item.get("title") or "-").strip()
        if severity_raw not in severity_examples or not title or title == "-":
            continue
        if title not in severity_examples[severity_raw]:
            severity_examples[severity_raw].append(title)

    enriched: list[str] = []
    for factor in base_factors:
        updated = factor
        upper_text = factor.upper()
        if "MEDIUM 리스크 이벤트" in factor and severity_examples["medium"]:
            updated = f"{factor}\n" + "\n".join(severity_examples["medium"][:3])
        elif "HIGH 리스크 이벤트" in factor and severity_examples["high"]:
            updated = f"{factor}\n" + "\n".join(severity_examples["high"][:3])
        elif "CRITICAL 리스크 이벤트" in factor and severity_examples["critical"]:
            updated = f"{factor}\n" + "\n".join(severity_examples["critical"][:3])
        elif "LOW 리스크 이벤트" in factor and severity_examples["low"]:
            updated = f"{factor}\n" + "\n".join(severity_examples["low"][:3])
        elif "리스크 이벤트" in factor and "MEDIUM" in upper_text and severity_examples["medium"]:
            updated = f"{factor}\n" + "\n".join(severity_examples["medium"][:3])
        enriched.append(updated)
    return enriched


def _build_recent_trend_summary(context: dict[str, Any]) -> str:
    trend = context.get("financial_trend", {})
    if not isinstance(trend, dict):
        trend = {}
    yoy = trend.get("yoy", {})
    if not isinstance(yoy, dict):
        yoy = {}

    pieces = []
    revenue_growth = _latest_number(yoy.get("revenue_growth"))
    asset_growth = _latest_number(yoy.get("asset_growth"))
    debt_change = _latest_number(yoy.get("debt_ratio"))
    op_margin_change = _latest_number(yoy.get("op_margin"))

    if revenue_growth is not None:
        direction = "증가" if revenue_growth >= 0 else "감소"
        pieces.append(f"최근 매출은 전년 대비 {abs(revenue_growth):.1f}% {direction}했습니다.")
    if asset_growth is not None:
        direction = "확대" if asset_growth >= 0 else "축소"
        pieces.append(f"총자산 규모는 전년 대비 {abs(asset_growth):.1f}% {direction}되었습니다.")
    if debt_change is not None:
        direction = "상승" if debt_change >= 0 else "하락"
        pieces.append(f"부채비율은 최근 {abs(debt_change):.1f}%p {direction}했습니다.")
    if op_margin_change is not None:
        direction = "개선" if op_margin_change >= 0 else "저하"
        pieces.append(f"영업이익률은 최근 {abs(op_margin_change):.1f}%p {direction}되었습니다.")

    return " ".join(pieces) or "최근 성장 및 추세를 해석할 수 있는 전년 대비 데이터가 충분하지 않습니다."


def _build_trend_history_rows(context: dict[str, Any]) -> list[tuple[str, str, str, str, str, str, str]]:
    trend = context.get("financial_trend", {})
    if not isinstance(trend, dict):
        trend = {}
    history = trend.get("history", [])
    if not isinstance(history, list):
        return []

    normalized_rows: list[tuple[int, str, str, str, str, str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        year_value = item.get("year")
        try:
            year_int = int(year_value)
        except (TypeError, ValueError):
            year_int = -1
        normalized_rows.append(
            (
                year_int,
                _format_currency(item.get("total_assets")),
                _format_currency(item.get("total_equity")),
                _format_currency(item.get("total_assets_statement", item.get("total_assets"))),
                _format_currency(item.get("revenue")),
                _format_currency(item.get("operating_income")),
                _format_currency(item.get("net_income")),
            )
        )
    sorted_rows = sorted(normalized_rows, key=lambda item: item[0], reverse=True)
    return [
        (
            str(year),
            total_assets,
            total_equity,
            total_assets_statement,
            revenue,
            operating_income,
            net_income,
        )
        for year, total_assets, total_equity, total_assets_statement, revenue, operating_income, net_income in sorted_rows[:3]
    ]


def _build_trend_chart_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    trend = context.get("financial_trend", {})
    if not isinstance(trend, dict):
        trend = {}
    history = trend.get("history", [])
    if not isinstance(history, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        year_value = item.get("year")
        try:
            year_int = int(year_value)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "year": year_int,
                "revenue": _to_float(item.get("revenue")),
                "operating_income": _to_float(item.get("operating_income")),
                "net_income": _to_float(item.get("net_income")),
                "total_assets": _to_float(item.get("total_assets")),
                "total_equity": _to_float(item.get("total_equity")),
            }
        )
    return sorted(rows, key=lambda row: row["year"])


def _latest_number(value: Any) -> float | None:
    if not isinstance(value, list) or not value:
        return None
    candidate = value[-1]
    try:
        return float(candidate)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _format_decision(decision: Any) -> str:
    return {
        "approve": "승인",
        "review": "재검토",
        "reject": "거절",
    }.get(str(decision), str(decision or "-"))


def _format_risk_level(level: Any) -> str:
    normalized = _normalize_severity(level)
    return {
        "critical": "CRITICAL(매우 높음)",
        "high": "HIGH(높음)",
        "medium": "MEDIUM(보통)",
        "low": "LOW(낮음)",
        "safe": "SAFE(안정)",
        "grey": "GREY(경계)",
        "distress": "DISTRESS(위험)",
        "positive": "POSITIVE(긍정)",
    }.get(normalized or str(level).lower(), str(level or "-"))


def _format_confidence(confidence: Any) -> str:
    if confidence is None:
        return "-"
    try:
        return f"{float(confidence) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(confidence)


def _format_currency(amount: Any) -> str:
    if amount in (None, ""):
        return "-"
    try:
        numeric_amount = int(float(amount))
    except (TypeError, ValueError):
        return str(amount)
    return f"{numeric_amount:,}원"


def _format_percent(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):,.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _format_ratio(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):,.2f}배"
    except (TypeError, ValueError):
        return str(value)


def _format_decimal(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
