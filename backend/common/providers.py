from __future__ import annotations

import math
from importlib import import_module
from types import ModuleType
from typing import Any, Protocol

from backend.data.services.sme_repository import (
    get_financial_rows_by_corp_code as get_financial_rows_by_corp_code_from_db,
)
from backend.data.services.sme_repository import (
    get_statement_detail_rows_by_corp_code as get_statement_detail_rows_by_corp_code_from_db,
)


class FinancialDataProvider(Protocol):
    """재무 분석 에이전트가 의존하는 데이터 제공 계약."""

    def get_financial_statements(self, corp_code: str, year: int) -> dict[str, Any]: ...

    def calc_financial_ratios(self, fs: dict[str, Any]) -> dict[str, Any]: ...

    def calc_altman_z_prime(self, fs: dict[str, Any]) -> dict[str, Any]: ...

    def trend_analysis(self, corp_code: str, years: list[int]) -> dict[str, Any]: ...

    def apply_risk_filters(
        self,
        fs: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


class IndustryDataProvider(Protocol):
    """산업 분석 에이전트가 의존하는 데이터 제공 계약."""

    def map_corp_to_ksic(self, corp_code: str) -> dict[str, Any]: ...

    def get_industry_avg_ratios(
        self,
        ksic_code: str,
        year: int,
        company_ratios: Any,
    ) -> dict[str, Any]: ...

    def get_industry_outlook(self, ksic_code: str) -> dict[str, Any]: ...

    def get_business_cycle(self) -> dict[str, Any]: ...

    def get_macro_indicators(self, ksic_code: str) -> dict[str, Any]: ...


class NewsCollectionProvider(Protocol):
    """뉴스 수집 에이전트가 의존하는 파이프라인 계약."""

    def execute_news_pipeline(
        self,
        *,
        database_url: str | None,
        lookback_days: int,
        max_articles: int,
        summarize: bool,
        model_name: str,
        company_limit: Any,
        show_progress: bool,
        company_name: Any,
        corp_name: Any,
        stock_code: Any,
        request_id: Any,
    ) -> dict[str, Any]: ...


def _load_financial_tools() -> ModuleType:
    return import_module("backend.tools.financial")


def _load_industry_tools() -> ModuleType:
    return import_module("backend.tools.industry")


def _load_news_tools() -> ModuleType:
    return import_module("backend.tools.news")


class ToolFinancialDataProvider:
    """기존 재무 tool 구현을 감싼 기본 provider."""

    def get_financial_statements(self, corp_code: str, year: int) -> dict[str, Any]:
        financial_tools = _load_financial_tools()
        return financial_tools.get_financial_statements.invoke(
            {"corp_code": corp_code, "year": year}
        )

    def calc_financial_ratios(self, fs: dict[str, Any]) -> dict[str, Any]:
        financial_tools = _load_financial_tools()
        return financial_tools.calc_financial_ratios.invoke({"fs": fs})

    def calc_altman_z_prime(self, fs: dict[str, Any]) -> dict[str, Any]:
        financial_tools = _load_financial_tools()
        return financial_tools.calc_altman_z_prime.invoke({"fs": fs})

    def trend_analysis(self, corp_code: str, years: list[int]) -> dict[str, Any]:
        financial_tools = _load_financial_tools()
        return financial_tools.trend_analysis.invoke(
            {"corp_code": corp_code, "years": years}
        )

    def apply_risk_filters(
        self,
        fs: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        financial_tools = _load_financial_tools()
        return financial_tools.apply_risk_filters.invoke(
            {"fs": fs, "history": history}
        )


class DatabaseFinancialDataProvider:
    """적재된 상세 재무 테이블을 우선 사용하고 legacy 요약 테이블을 보조로 쓴다."""

    def get_financial_statements(self, corp_code: str, year: int) -> dict[str, Any]:
        """DB의 연도별 상세 재무 스냅샷에서 기준 연도 재무제표 dict를 구성한다."""
        rows = _load_statement_detail_rows(corp_code)
        if not rows:
            rows = _load_financial_rows(corp_code)
        selected_row = _select_target_row(rows, year)
        if selected_row is None:
            raise ValueError(f"corp_code={corp_code}, year={year} 재무 데이터 없음")
        return _build_financial_statement(selected_row)

    def calc_financial_ratios(self, fs: dict[str, Any]) -> dict[str, Any]:
        """기존 재무 도구 로직으로 주요 비율을 계산한다."""
        financial_tools = _load_financial_tools()
        return financial_tools.calc_financial_ratios.invoke({"fs": fs})

    def calc_altman_z_prime(self, fs: dict[str, Any]) -> dict[str, Any]:
        """기존 재무 도구 로직으로 Altman Z'를 계산한다."""
        financial_tools = _load_financial_tools()
        return financial_tools.calc_altman_z_prime.invoke({"fs": fs})

    def trend_analysis(self, corp_code: str, years: list[int]) -> dict[str, Any]:
        """DB의 연도별 재무 피처를 기반으로 추세와 플래그를 계산한다."""
        rows = _load_statement_detail_rows(corp_code)
        if not rows:
            rows = _load_financial_rows(corp_code)
        rows_by_year = _index_rows_by_year(rows)
        history: list[dict[str, Any]] = []
        flags: list[str] = []

        for year in sorted(years):
            row = rows_by_year.get(year)
            if row is None:
                flags.append(f"{year}_data_missing")
                continue

            fs = _build_financial_statement(row)
            ratios = self.calc_financial_ratios(fs)

            history.append(
                {
                    "year": year,
                    "debt_ratio": ratios.get("debt_ratio"),
                    "op_margin": ratios.get("op_margin"),
                    "icr": ratios.get("interest_coverage"),
                    "revenue": fs.get("매출액"),
                    "net_income": fs.get("당기순이익"),
                    "total_assets": fs.get("총자산"),
                    "ocf": fs.get("영업현금흐름"),
                }
            )

        yoy = {
            "debt_ratio": [],
            "op_margin": [],
            "revenue_growth": [],
            "asset_growth": [],
        }

        for previous, current in zip(history, history[1:]):
            current_year = int(current["year"])

            debt_change = _safe_delta(
                previous.get("debt_ratio"),
                current.get("debt_ratio"),
            )
            margin_change = _safe_delta(
                previous.get("op_margin"),
                current.get("op_margin"),
            )
            revenue_growth = _safe_growth(
                previous.get("revenue"),
                current.get("revenue"),
            )
            asset_growth = _safe_growth(
                previous.get("total_assets"),
                current.get("total_assets"),
            )

            yoy["debt_ratio"].append(debt_change)
            yoy["op_margin"].append(margin_change)
            yoy["revenue_growth"].append(revenue_growth)
            yoy["asset_growth"].append(asset_growth)

            if debt_change is not None and debt_change >= 0.20:
                flags.append(f"{current_year}_debt_ratio_spike_+{debt_change:.0%}")
            if margin_change is not None and margin_change <= -0.05:
                flags.append(f"{current_year}_op_margin_drop_{margin_change:.0%}")
            if revenue_growth is not None and revenue_growth <= -0.10:
                flags.append(f"{current_year}_revenue_drop_{revenue_growth:.0%}")
            if current.get("ocf") is not None and current.get("ocf", 0) < 0:
                flags.append(f"{current_year}_negative_operating_cashflow")

        if history:
            latest = history[-1]
            current_year = int(latest["year"])
            icr = latest.get("icr")
            if icr is not None:
                if icr < 1.0:
                    flags.append(f"{current_year}_icr_danger_{icr:.2f}")
                elif icr < 1.5:
                    flags.append(f"{current_year}_icr_caution_{icr:.2f}")
            debt_ratio = latest.get("debt_ratio")
            if debt_ratio is not None:
                if debt_ratio >= 3.0:
                    flags.append(f"{current_year}_debt_ratio_danger_{debt_ratio:.0%}")
                elif debt_ratio >= 2.0:
                    flags.append(f"{current_year}_debt_ratio_caution_{debt_ratio:.0%}")

        growth_ratios: dict[str, float | None] = {
            "revenue_growth": yoy["revenue_growth"][-1] if yoy["revenue_growth"] else None,
            "asset_growth": yoy["asset_growth"][-1] if yoy["asset_growth"] else None,
            "net_income_growth": None,
            "tangible_asset_growth": None,
        }
        if len(history) >= 2:
            latest = history[-1]
            previous = history[-2]
            growth_ratios["net_income_growth"] = _safe_growth(
                previous.get("net_income"),
                latest.get("net_income"),
            )

        return {
            "flags": flags,
            "yoy": yoy,
            "history": history,
            "growth_ratios": growth_ratios,
        }

    def apply_risk_filters(
        self,
        fs: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """기존 리스크 필터 로직을 재사용해 등급 상한을 계산한다."""
        financial_tools = _load_financial_tools()
        return financial_tools.apply_risk_filters.invoke(
            {"fs": fs, "history": history}
        )


class ToolIndustryDataProvider:
    """기존 산업 tool 구현을 감싼 기본 provider."""

    def map_corp_to_ksic(self, corp_code: str) -> dict[str, Any]:
        industry_tools = _load_industry_tools()
        return industry_tools.map_corp_to_ksic.invoke({"corp_code": corp_code})

    def get_industry_avg_ratios(
        self,
        ksic_code: str,
        year: int,
        company_ratios: Any,
    ) -> dict[str, Any]:
        industry_tools = _load_industry_tools()
        return industry_tools.get_industry_avg_ratios.invoke(
            {
                "ksic_code": ksic_code,
                "year": year,
                "company_ratios": company_ratios,
            }
        )

    def get_industry_outlook(self, ksic_code: str) -> dict[str, Any]:
        industry_tools = _load_industry_tools()
        return industry_tools.get_industry_outlook.invoke({"ksic_code": ksic_code})

    def get_business_cycle(self) -> dict[str, Any]:
        industry_tools = _load_industry_tools()
        return industry_tools.get_business_cycle.invoke({})

    def get_macro_indicators(self, ksic_code: str) -> dict[str, Any]:
        industry_tools = _load_industry_tools()
        return industry_tools.get_macro_indicators.invoke({"ksic_code": ksic_code})


class ToolNewsCollectionProvider:
    """기존 뉴스 수집 파이프라인을 감싼 기본 provider."""

    def execute_news_pipeline(
        self,
        *,
        database_url: str | None,
        lookback_days: int,
        max_articles: int,
        summarize: bool,
        model_name: str,
        company_limit: Any,
        show_progress: bool,
        company_name: Any,
        corp_name: Any,
        stock_code: Any,
        request_id: Any,
    ) -> dict[str, Any]:
        news_tools = _load_news_tools()
        return news_tools.execute_news_pipeline(
            database_url=database_url,
            lookback_days=lookback_days,
            max_articles=max_articles,
            summarize=summarize,
            model_name=model_name,
            company_limit=company_limit,
            show_progress=show_progress,
            company_name=company_name,
            corp_name=corp_name,
            stock_code=stock_code,
            request_id=request_id,
        )


def _load_financial_rows(corp_code: str) -> list[dict[str, Any]]:
    return get_financial_rows_by_corp_code_from_db(corp_code)


def _load_statement_detail_rows(corp_code: str) -> list[dict[str, Any]]:
    return get_statement_detail_rows_by_corp_code_from_db(corp_code)


def _select_target_row(
    rows: list[dict[str, Any]],
    target_year: int,
) -> dict[str, Any] | None:
    normalized_rows = sorted(
        rows,
        key=lambda row: _to_int(row.get("year")) or 0,
    )
    if not normalized_rows:
        return None

    exact_match = next(
        (row for row in normalized_rows if _to_int(row.get("year")) == target_year),
        None,
    )
    if exact_match is not None:
        return exact_match

    prior_rows = [
        row
        for row in normalized_rows
        if (_to_int(row.get("year")) or 0) <= target_year
    ]
    if prior_rows:
        return prior_rows[-1]
    return normalized_rows[-1]


def _index_rows_by_year(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {
        year: row
        for row in rows
        if (year := _to_int(row.get("year"))) is not None
    }


def _build_financial_statement(row: dict[str, Any]) -> dict[str, Any]:
    current_assets = _coalesce_amount(row.get("current_assets"))
    current_liabilities = _coalesce_amount(row.get("current_liabilities"))
    total_assets = _coalesce_amount(
        row.get("total_assets_statement"),
        row.get("total_assets"),
    )
    total_equity = _coalesce_amount(row.get("total_equity"))
    total_liabilities = _coalesce_amount(row.get("total_liabilities"))
    retained_earnings = _coalesce_amount(row.get("retained_earnings"))
    inventory = _coalesce_amount(row.get("inventory"))
    accounts_receivable = _coalesce_amount(row.get("accounts_receivable"))
    accounts_payable = _coalesce_amount(row.get("accounts_payable"))
    short_term_borrowings = _coalesce_amount(row.get("short_term_borrowings"))
    current_portion_long_term_borrowings = _coalesce_amount(
        row.get("current_portion_long_term_borrowings")
    )
    long_term_borrowings = _coalesce_amount(row.get("long_term_borrowings"))
    bonds = _coalesce_amount(row.get("bonds"))
    tangible_assets = _coalesce_amount(row.get("tangible_assets"))
    revenue = _coalesce_amount(row.get("revenue"))
    cost_of_goods_sold = _coalesce_amount(row.get("cost_of_goods_sold"))
    operating_income = _coalesce_amount(row.get("operating_income"))
    net_income = _coalesce_amount(row.get("net_income"))
    interest_expense = _coalesce_amount(row.get("interest_expense"))
    operating_cashflow = _coalesce_amount(row.get("operating_cashflow"))
    capital_expenditure = _coalesce_amount(row.get("capital_expenditure"))

    return {
        "회사명": row.get("corp_name"),
        "사업연도": _to_int(row.get("year")),
        "총자산": total_assets or 0.0,
        "유동자산": current_assets or 0.0,
        "유동부채": current_liabilities or 0.0,
        "자본총계": total_equity or 0.0,
        "부채총계": total_liabilities or 0.0,
        "이익잉여금": retained_earnings or 0.0,
        "재고자산": inventory or 0.0,
        "매출채권": accounts_receivable or 0.0,
        "매입채무": accounts_payable or 0.0,
        "단기차입금": short_term_borrowings or 0.0,
        "유동성장기차입금": current_portion_long_term_borrowings or 0.0,
        "장기차입금": long_term_borrowings or 0.0,
        "사채": bonds or 0.0,
        "유형자산": tangible_assets or 0.0,
        "매출액": revenue or 0.0,
        "매출원가": cost_of_goods_sold or 0.0,
        "영업이익": operating_income or 0.0,
        "당기순이익": net_income or 0.0,
        "이자비용": interest_expense or 0.0,
        "영업현금흐름": operating_cashflow or 0.0,
        "유형자산취득": capital_expenditure or 0.0,
        "avg_revenue_last_3y": _to_float(row.get("avg_revenue_last_3y")),
        "audit_opinion": row.get("audit_opinion"),
        "is_external_audit": _to_bool(row.get("is_external_audit")),
        "is_small_enterprise": False,
        "is_individual": False,
        "total_assets_statement": total_assets or 0.0,
    }


def _coalesce_amount(*values: Any) -> float | None:
    for value in values:
        amount = _to_float(value)
        if amount is not None:
            return amount
    return None


def _safe_ratio(
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _safe_delta(
    previous: float | None,
    current: float | None,
) -> float | None:
    if previous is None or current is None:
        return None
    return current - previous


def _safe_growth(
    previous: float | None,
    current: float | None,
) -> float | None:
    if previous is None or current is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}
