"""R-NEW | 재무 이상 징후 탐지 핸들러

financial_features.csv (또는 DB)에서 가져온 재무 데이터를 기반으로
부채 급증 / 순이익 적자 전환 / 영업이익 급감 / 매출 감소 / 자본잠식을 탐지한다.
"""

from __future__ import annotations

import logging
import math
from datetime import date

from ..models import EventSource, EventType, FinancialAnomalyResult, RiskEvent

logger = logging.getLogger(__name__)

DEBT_RATIO_SPIKE_THRESHOLD = 0.20
OP_INCOME_DROP_THRESHOLD   = -0.30
REVENUE_DECLINE_THRESHOLD  = -0.10


class _YearlyFinancials:
    __slots__ = (
        "year", "revenue", "operating_income", "net_income",
        "total_assets", "total_liabilities", "total_equity",
    )

    def __init__(self, row: dict) -> None:
        self.year              = int(row["year"])
        self.revenue           = _f(row, "revenue")
        self.operating_income  = _f(row, "operating_income")
        self.net_income        = _f(row, "net_income")
        self.total_assets      = _f(row, "total_assets_statement")
        self.total_liabilities = _f(row, "total_liabilities")
        self.total_equity      = _f(row, "total_equity")

    @property
    def debt_ratio(self) -> float | None:
        if self.total_equity and self.total_equity != 0:
            return self.total_liabilities / self.total_equity * 100
        return None

    @property
    def operating_margin(self) -> float | None:
        if self.revenue and self.revenue != 0:
            return self.operating_income / self.revenue * 100
        return None


def detect_financial_anomalies(
    company_name: str,
    corp_code: str,
    financial_rows: list[dict],
) -> FinancialAnomalyResult:
    if not financial_rows:
        logger.warning("[%s] 재무 데이터 없음 — 이상 탐지 건너뜀", company_name)
        return FinancialAnomalyResult(company_name=company_name, corp_code=corp_code)

    records = sorted([_YearlyFinancials(r) for r in financial_rows], key=lambda r: r.year)
    events: list[RiskEvent] = []

    # 1. 부채비율 급증
    for prev, curr in zip(records, records[1:]):
        if prev.debt_ratio is None or curr.debt_ratio is None:
            continue
        delta_pp = curr.debt_ratio - prev.debt_ratio
        if delta_pp / 100 >= DEBT_RATIO_SPIKE_THRESHOLD:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"부채비율 급증 ({prev.year}→{curr.year})",
                description=f"부채비율 {prev.debt_ratio:.1f}% → {curr.debt_ratio:.1f}% ({delta_pp:+.1f}%p)",
                detected_at=date(curr.year, 12, 31),
                raw_value=curr.debt_ratio,
                delta_value=delta_pp,
            ))

    # 2. 영업이익 급감
    for prev, curr in zip(records, records[1:]):
        if prev.operating_income == 0:
            continue
        chg = (curr.operating_income - prev.operating_income) / abs(prev.operating_income)
        if chg <= OP_INCOME_DROP_THRESHOLD:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"영업이익 급감 ({prev.year}→{curr.year})",
                description=f"영업이익 {_fmt(prev.operating_income)} → {_fmt(curr.operating_income)} ({chg*100:.1f}%)",
                detected_at=date(curr.year, 12, 31),
                raw_value=curr.operating_income,
                delta_value=chg,
            ))

    # 3. 당기순이익 적자 전환
    for prev, curr in zip(records, records[1:]):
        if prev.net_income >= 0 and curr.net_income < 0:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"당기순이익 적자 전환 ({curr.year})",
                description=f"당기순이익 {_fmt(prev.net_income)}(흑자) → {_fmt(curr.net_income)}(적자)",
                detected_at=date(curr.year, 12, 31),
                raw_value=curr.net_income,
                delta_value=curr.net_income - prev.net_income,
            ))

    # 4. 매출 감소
    for prev, curr in zip(records, records[1:]):
        if prev.revenue == 0:
            continue
        chg = (curr.revenue - prev.revenue) / abs(prev.revenue)
        if chg <= REVENUE_DECLINE_THRESHOLD:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"매출 감소 ({prev.year}→{curr.year})",
                description=f"매출 {_fmt(prev.revenue)} → {_fmt(curr.revenue)} ({chg*100:.1f}%)",
                detected_at=date(curr.year, 12, 31),
                raw_value=curr.revenue,
                delta_value=chg,
            ))

    # 5. 자본잠식
    for r in records:
        if r.total_equity < 0:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"자본잠식 ({r.year})",
                description=f"자본총계 {_fmt(r.total_equity)} — 완전 자본잠식",
                detected_at=date(r.year, 12, 31),
                raw_value=r.total_equity,
            ))

    latest = records[-1]
    return FinancialAnomalyResult(
        company_name=company_name,
        corp_code=corp_code,
        anomalies=events,
        years_analyzed=[r.year for r in records],
        latest_debt_ratio=latest.debt_ratio,
        latest_op_margin=latest.operating_margin,
        is_net_income_negative=latest.net_income < 0,
    )


def _f(row: dict, key: str) -> float:
    v = row.get(key, 0) or 0
    return float(v) if not (isinstance(v, float) and math.isnan(v)) else 0.0


def _fmt(amount: float) -> str:
    if abs(amount) >= 1_000_000_000_000:
        return f"{amount / 1_000_000_000_000:.1f}조원"
    if abs(amount) >= 100_000_000:
        return f"{amount / 100_000_000:.0f}억원"
    return f"{amount:,.0f}원"
