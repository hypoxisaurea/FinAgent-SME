"""R-NEW | 재무 이상 징후 탐지 핸들러

financial_features.csv (또는 DB)에서 가져온 재무 데이터를 기반으로
부채 급증 / 순이익 적자 전환 / 영업이익 급감 / 현금흐름 악화 등
이상 패턴을 탐지한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from ..models import RiskEvent, EventSource, EventType


# ─── 임계값 상수 ──────────────────────────────────────────────────────────────

DEBT_RATIO_SPIKE_THRESHOLD = 0.20       # 부채비율 YoY 20%p 이상 증가
OP_INCOME_DROP_THRESHOLD = -0.30        # 영업이익 YoY 30% 이상 감소
NET_INCOME_NEGATIVE = 0                 # 당기순이익 0 미만 → 적자 전환
REVENUE_DECLINE_THRESHOLD = -0.10      # 매출 YoY 10% 이상 감소


# ─── 내부 DTO ────────────────────────────────────────────────────────────────

@dataclass
class YearlyFinancials:
    year: int
    revenue: float
    operating_income: float
    net_income: float
    total_assets: float
    total_liabilities: float
    total_equity: float

    @property
    def debt_ratio(self) -> float | None:
        """부채비율 = 부채 / 자본 × 100"""
        if self.total_equity and self.total_equity != 0:
            return self.total_liabilities / self.total_equity * 100
        return None

    @property
    def operating_margin(self) -> float | None:
        """영업이익률 = 영업이익 / 매출 × 100"""
        if self.revenue and self.revenue != 0:
            return self.operating_income / self.revenue * 100
        return None


@dataclass
class FinancialAnomalyResult:
    company_name: str
    corp_code: str
    anomalies: list[RiskEvent] = field(default_factory=list)
    analyzed_at: date = field(default_factory=date.today)
    years_analyzed: list[int] = field(default_factory=list)
    # 요약 통계
    latest_debt_ratio: float | None = None
    latest_op_margin: float | None = None
    is_net_income_negative: bool = False


# ─── 핸들러 ──────────────────────────────────────────────────────────────────

def detect_financial_anomalies(
    company_name: str,
    corp_code: str,
    financial_rows: list[dict],  # financial_features.csv 행 목록
) -> FinancialAnomalyResult:
    """재무 이상 징후를 탐지하고 RiskEvent 목록으로 반환한다.

    Args:
        company_name: 기업명
        corp_code: DART 고유번호
        financial_rows: financial_features.csv에서 필터링한 해당 기업 행 목록
            필수 컬럼: year, revenue, operating_income, net_income,
                      total_assets_statement, total_liabilities, total_equity
    """
    result = FinancialAnomalyResult(
        company_name=company_name,
        corp_code=corp_code,
    )

    if not financial_rows:
        return result

    # 연도 오름차순 정렬
    records = sorted(
        [_row_to_dto(r) for r in financial_rows],
        key=lambda r: r.year,
    )
    result.years_analyzed = [r.year for r in records]

    # 최신 연도 지표 저장
    latest = records[-1]
    result.latest_debt_ratio = latest.debt_ratio
    result.latest_op_margin = latest.operating_margin
    result.is_net_income_negative = latest.net_income < 0

    events: list[RiskEvent] = []

    # ── 1. 부채비율 급증 탐지 (YoY) ──────────────────────────────────────────
    for prev, curr in zip(records, records[1:]):
        if prev.debt_ratio is None or curr.debt_ratio is None:
            continue
        delta = (curr.debt_ratio - prev.debt_ratio) / 100  # 비율 변화
        if delta >= DEBT_RATIO_SPIKE_THRESHOLD:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"부채비율 급증 ({prev.year}→{curr.year})",
                description=(
                    f"부채비율이 {prev.debt_ratio:.1f}%에서 "
                    f"{curr.debt_ratio:.1f}%로 "
                    f"{curr.debt_ratio - prev.debt_ratio:.1f}%p 상승했습니다."
                ),
                detected_at=date(curr.year, 12, 31),
                raw_value=curr.debt_ratio,
                delta_value=curr.debt_ratio - prev.debt_ratio,
            ))

    # ── 2. 영업이익 급감 탐지 (YoY) ──────────────────────────────────────────
    for prev, curr in zip(records, records[1:]):
        if prev.operating_income == 0:
            continue
        chg = (curr.operating_income - prev.operating_income) / abs(prev.operating_income)
        if chg <= OP_INCOME_DROP_THRESHOLD:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"영업이익 급감 ({prev.year}→{curr.year})",
                description=(
                    f"영업이익이 {_fmt_won(prev.operating_income)}에서 "
                    f"{_fmt_won(curr.operating_income)}으로 "
                    f"{chg * 100:.1f}% 감소했습니다."
                ),
                detected_at=date(curr.year, 12, 31),
                raw_value=curr.operating_income,
                delta_value=chg,
            ))

    # ── 3. 당기순이익 적자 전환 탐지 ──────────────────────────────────────────
    for prev, curr in zip(records, records[1:]):
        if prev.net_income >= 0 and curr.net_income < 0:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"당기순이익 적자 전환 ({curr.year})",
                description=(
                    f"당기순이익이 {_fmt_won(prev.net_income)}(흑자)에서 "
                    f"{_fmt_won(curr.net_income)}(적자)으로 전환되었습니다."
                ),
                detected_at=date(curr.year, 12, 31),
                raw_value=curr.net_income,
                delta_value=curr.net_income - prev.net_income,
            ))

    # ── 4. 매출 감소 탐지 (YoY) ───────────────────────────────────────────────
    for prev, curr in zip(records, records[1:]):
        if prev.revenue == 0:
            continue
        chg = (curr.revenue - prev.revenue) / abs(prev.revenue)
        if chg <= REVENUE_DECLINE_THRESHOLD:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"매출 감소 ({prev.year}→{curr.year})",
                description=(
                    f"매출액이 {_fmt_won(prev.revenue)}에서 "
                    f"{_fmt_won(curr.revenue)}으로 "
                    f"{chg * 100:.1f}% 감소했습니다."
                ),
                detected_at=date(curr.year, 12, 31),
                raw_value=curr.revenue,
                delta_value=chg,
            ))

    # ── 5. 자본잠식 탐지 ──────────────────────────────────────────────────────
    for record in records:
        if record.total_equity < 0:
            events.append(RiskEvent(
                event_type=EventType.FINANCIAL_ANOMALY,
                source=EventSource.FINANCIAL_DATA,
                title=f"자본잠식 ({record.year})",
                description=(
                    f"{record.year}년 자본총계가 {_fmt_won(record.total_equity)}으로 "
                    "완전 자본잠식 상태입니다."
                ),
                detected_at=date(record.year, 12, 31),
                raw_value=record.total_equity,
                delta_value=None,
            ))

    result.anomalies = events
    return result


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _row_to_dto(row: dict) -> YearlyFinancials:
    def _f(key: str) -> float:
        v = row.get(key, 0) or 0
        return float(v) if not (isinstance(v, float) and math.isnan(v)) else 0.0

    return YearlyFinancials(
        year=int(row["year"]),
        revenue=_f("revenue"),
        operating_income=_f("operating_income"),
        net_income=_f("net_income"),
        total_assets=_f("total_assets_statement"),
        total_liabilities=_f("total_liabilities"),
        total_equity=_f("total_equity"),
    )


def _fmt_won(amount: float) -> str:
    """원화 금액을 억 단위로 표시한다."""
    if abs(amount) >= 1_000_000_000_000:
        return f"{amount / 1_000_000_000_000:.1f}조원"
    if abs(amount) >= 100_000_000:
        return f"{amount / 100_000_000:.0f}억원"
    return f"{amount:,.0f}원"
