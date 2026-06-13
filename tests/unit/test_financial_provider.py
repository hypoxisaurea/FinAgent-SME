from __future__ import annotations

import asyncio

from backend.agents.financial_analyst.agent import FinancialAnalystAgent
import backend.common.providers as providers


def test_database_financial_provider_reads_financial_features_rows(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        providers,
        "get_statement_detail_rows_by_corp_code_from_db",
        lambda corp_code: [
            {
                "corp_code": corp_code,
                "corp_name": "테스트기업",
                "stock_code": "123456",
                "year": 2023,
                "avg_revenue_last_3y": 1_200_000_000,
                "current_assets": 700_000_000,
                "current_liabilities": 400_000_000,
                "revenue": 1_100_000_000,
                "cost_of_goods_sold": 700_000_000,
                "operating_income": 70_000_000,
                "net_income": -20_000_000,
                "total_assets_statement": 1_950_000_000,
                "total_liabilities": 1_300_000_000,
                "total_equity": 650_000_000,
                "retained_earnings": 200_000_000,
                "inventory": 100_000_000,
                "accounts_receivable": 150_000_000,
                "accounts_payable": 130_000_000,
                "short_term_borrowings": 250_000_000,
                "current_portion_long_term_borrowings": 50_000_000,
                "long_term_borrowings": 400_000_000,
                "bonds": 0,
                "tangible_assets": 500_000_000,
                "interest_expense": 40_000_000,
                "operating_cashflow": -10_000_000,
                "capital_expenditure": 40_000_000,
                "audit_opinion": None,
                "is_external_audit": False,
            },
            {
                "corp_code": corp_code,
                "corp_name": "테스트기업",
                "stock_code": "123456",
                "year": 2024,
                "avg_revenue_last_3y": 1_500_000_000,
                "current_assets": 800_000_000,
                "current_liabilities": 500_000_000,
                "revenue": 1_400_000_000,
                "cost_of_goods_sold": 860_000_000,
                "operating_income": 120_000_000,
                "net_income": -10_000_000,
                "total_assets_statement": 2_500_000_000,
                "total_liabilities": 2_000_000_000,
                "total_equity": 500_000_000,
                "retained_earnings": 150_000_000,
                "inventory": 120_000_000,
                "accounts_receivable": 170_000_000,
                "accounts_payable": 150_000_000,
                "short_term_borrowings": 300_000_000,
                "current_portion_long_term_borrowings": 60_000_000,
                "long_term_borrowings": 500_000_000,
                "bonds": 50_000_000,
                "tangible_assets": 650_000_000,
                "interest_expense": 50_000_000,
                "operating_cashflow": -20_000_000,
                "capital_expenditure": 50_000_000,
                "audit_opinion": None,
                "is_external_audit": False,
            },
        ],
    )
    monkeypatch.setattr(
        providers,
        "get_financial_rows_by_corp_code_from_db",
        lambda corp_code: [],
    )

    provider = providers.DatabaseFinancialDataProvider()

    fs = provider.get_financial_statements("00123456", 2024)
    ratios = provider.calc_financial_ratios(fs)
    trend = provider.trend_analysis("00123456", [2022, 2023, 2024])
    risk_filters = provider.apply_risk_filters(fs, trend["history"])

    assert fs["총자산"] == 2_500_000_000
    assert fs["매출액"] == 1_400_000_000
    assert ratios["debt_ratio"] == 4.0
    assert ratios["current_ratio"] == 800_000_000 / 500_000_000
    assert ratios["op_margin"] == 120_000_000 / 1_400_000_000
    assert trend["flags"][0] == "2022_data_missing"
    assert trend["growth_ratios"]["revenue_growth"] == (
        (1_400_000_000 - 1_100_000_000) / 1_100_000_000
    )
    assert any(flag.endswith("negative_operating_cashflow") for flag in trend["flags"])
    assert risk_filters["grade_cap"] == "B"
    assert "당기순손실_2년연속" in risk_filters["triggered_filters"]


def test_financial_agent_uses_database_provider_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        providers,
        "get_statement_detail_rows_by_corp_code_from_db",
        lambda corp_code: [
            {
                "corp_code": corp_code,
                "corp_name": "테스트기업",
                "stock_code": "123456",
                "year": 2022,
                "avg_revenue_last_3y": 3_100_000_000,
                "current_assets": 1_600_000_000,
                "current_liabilities": 900_000_000,
                "revenue": 2_800_000_000,
                "cost_of_goods_sold": 1_900_000_000,
                "operating_income": 220_000_000,
                "net_income": 100_000_000,
                "total_assets_statement": 4_900_000_000,
                "total_liabilities": 2_500_000_000,
                "total_equity": 2_400_000_000,
                "retained_earnings": 700_000_000,
                "inventory": 200_000_000,
                "accounts_receivable": 250_000_000,
                "accounts_payable": 200_000_000,
                "short_term_borrowings": 300_000_000,
                "current_portion_long_term_borrowings": 80_000_000,
                "long_term_borrowings": 500_000_000,
                "bonds": 0,
                "tangible_assets": 1_100_000_000,
                "interest_expense": 60_000_000,
                "operating_cashflow": 180_000_000,
                "capital_expenditure": 70_000_000,
                "audit_opinion": None,
                "is_external_audit": False,
            },
            {
                "corp_code": corp_code,
                "corp_name": "테스트기업",
                "stock_code": "123456",
                "year": 2023,
                "avg_revenue_last_3y": 3_200_000_000,
                "current_assets": 1_700_000_000,
                "current_liabilities": 850_000_000,
                "revenue": 3_100_000_000,
                "cost_of_goods_sold": 2_000_000_000,
                "operating_income": 260_000_000,
                "net_income": 130_000_000,
                "total_assets_statement": 5_200_000_000,
                "total_liabilities": 2_400_000_000,
                "total_equity": 2_800_000_000,
                "retained_earnings": 820_000_000,
                "inventory": 220_000_000,
                "accounts_receivable": 270_000_000,
                "accounts_payable": 210_000_000,
                "short_term_borrowings": 280_000_000,
                "current_portion_long_term_borrowings": 70_000_000,
                "long_term_borrowings": 450_000_000,
                "bonds": 0,
                "tangible_assets": 1_150_000_000,
                "interest_expense": 55_000_000,
                "operating_cashflow": 220_000_000,
                "capital_expenditure": 80_000_000,
                "audit_opinion": None,
                "is_external_audit": False,
            },
            {
                "corp_code": corp_code,
                "corp_name": "테스트기업",
                "stock_code": "123456",
                "year": 2024,
                "avg_revenue_last_3y": 3_500_000_000,
                "current_assets": 1_900_000_000,
                "current_liabilities": 800_000_000,
                "revenue": 3_600_000_000,
                "cost_of_goods_sold": 2_200_000_000,
                "operating_income": 330_000_000,
                "net_income": 180_000_000,
                "total_assets_statement": 5_700_000_000,
                "total_liabilities": 2_200_000_000,
                "total_equity": 3_500_000_000,
                "retained_earnings": 950_000_000,
                "inventory": 240_000_000,
                "accounts_receivable": 300_000_000,
                "accounts_payable": 230_000_000,
                "short_term_borrowings": 250_000_000,
                "current_portion_long_term_borrowings": 60_000_000,
                "long_term_borrowings": 400_000_000,
                "bonds": 0,
                "tangible_assets": 1_250_000_000,
                "interest_expense": 50_000_000,
                "operating_cashflow": 260_000_000,
                "capital_expenditure": 90_000_000,
                "audit_opinion": None,
                "is_external_audit": False,
            },
        ],
    )
    monkeypatch.setattr(
        providers,
        "get_financial_rows_by_corp_code_from_db",
        lambda corp_code: [],
    )

    result = asyncio.run(
        FinancialAnalystAgent().run(
            {
                "company_name": "테스트기업",
                "corp_code": "00123456",
                "request_id": "req-fin-db",
                "target_year": 2024,
            }
        )
    )

    assert result["status"] == "success"
    assert result["fallback_used"] is False
    assert result["financial_statements"]["매출액"] == 3_600_000_000
    assert result["avg_revenue_last_3y"] == 3_500_000_000
    assert result["company_ratios"]["sales_growth"] == (
        (3_600_000_000 - 3_100_000_000) / 3_100_000_000
    )
    assert result["altman_z"]["z_prime"] is not None
