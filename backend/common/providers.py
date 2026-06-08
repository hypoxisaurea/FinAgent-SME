from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any, Protocol


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
