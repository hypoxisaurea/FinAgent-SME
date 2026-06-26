from __future__ import annotations

import re
from pathlib import Path

import backend.tools.company_registry as company_registry
from backend.tools.news import DaumNewsArticle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ERD_PATH = PROJECT_ROOT / "docs" / "design" / "erd.md"


def test_erd_mermaid_columns_match_code_sources() -> None:
    erd_columns = _extract_mermaid_columns(ERD_PATH.read_text())

    assert erd_columns["SME_LIST"] == [
        "corp_code",
        "corp_name",
        "stock_code",
        "avg_revenue_last_3y",
        "total_assets",
        "created_at",
    ]
    assert erd_columns["COMPANY_PROFILES"] == [
        "corp_code",
        *company_registry.COMPANY_PROFILE_COLUMNS,
        "created_at",
    ]
    assert erd_columns["FINANCIAL_FEATURES"] == [
        "corp_code",
        "corp_name",
        "stock_code",
        "year",
        "avg_revenue_last_3y",
        "total_assets",
        "revenue",
        "operating_income",
        "net_income",
        "total_assets_statement",
        "total_liabilities",
        "total_equity",
        "created_at",
    ]
    assert erd_columns["FINANCIAL_STATEMENT_DETAILS"] == (
        company_registry.STATEMENT_DETAIL_COLUMNS
    )
    assert erd_columns["DAUM_NEWS_ARTICLES"] == [
        column.name for column in DaumNewsArticle.__table__.columns
    ]
    assert erd_columns["FINANCIAL_ERROR_LOGS"] == [
        "error_datetime",
        "corp_code",
        "corp_name",
        "error_type",
        "message",
        "response",
        "traceback",
    ]
    assert erd_columns["WORKFLOW_JOBS"] == [
        "job_id",
        "request_id",
        "company_name",
        "status",
        "result_json",
        "step_summary_json",
        "error_code",
        "error_message",
        "submitted_at",
        "started_at",
        "finished_at",
        "updated_at",
    ]


def _extract_mermaid_columns(text: str) -> dict[str, list[str]]:
    blocks = re.findall(r"    ([A-Z_]+) \{\n(.*?)\n    \}", text, re.S)
    return {
        table_name: [
            line.strip().split()[1]
            for line in block.splitlines()
            if line.strip()
        ]
        for table_name, block in blocks
    }
