from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text

from backend.data.db import FEATURES_TABLE_NAME
from backend.data.repositories.company_registry import save_dataframe_to_postgres


def test_save_dataframe_to_postgres_replaces_existing_rows_by_key() -> None:
    engine = create_engine("sqlite:///:memory:")
    initial_df = pd.DataFrame(
        [
            {
                "corp_code": "001",
                "stock_code": "111111",
                "year": 2024,
                "revenue": 100,
                "created_at": "2026-06-01",
            }
        ]
    )
    updated_df = pd.DataFrame(
        [
            {
                "corp_code": "001",
                "stock_code": "111111",
                "year": 2024,
                "revenue": 250,
                "created_at": "2026-06-10",
            }
        ]
    )

    first_count = save_dataframe_to_postgres(
        initial_df,
        engine,
        FEATURES_TABLE_NAME,
        ["corp_code", "stock_code", "year"],
    )
    second_count = save_dataframe_to_postgres(
        updated_df,
        engine,
        FEATURES_TABLE_NAME,
        ["corp_code", "stock_code", "year"],
    )

    saved_df = pd.read_sql(
        text(
            f"""
            SELECT corp_code, stock_code, year, revenue, created_at
            FROM {FEATURES_TABLE_NAME}
            """
        ),
        engine,
    )

    assert first_count == 1
    assert second_count == 1
    assert len(saved_df) == 1
    assert saved_df.iloc[0]["revenue"] == 250
    assert saved_df.iloc[0]["created_at"] == "2026-06-10"


def test_save_dataframe_to_postgres_upserts_new_and_existing_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    initial_df = pd.DataFrame(
        [
            {
                "corp_code": "001",
                "stock_code": "111111",
                "year": 2024,
                "revenue": 100,
                "created_at": "2026-06-01",
            }
        ]
    )
    next_df = pd.DataFrame(
        [
            {
                "corp_code": "001",
                "stock_code": "111111",
                "year": 2024,
                "revenue": 300,
                "created_at": "2026-06-10",
            },
            {
                "corp_code": "002",
                "stock_code": "222222",
                "year": 2024,
                "revenue": 400,
                "created_at": "2026-06-10",
            },
        ]
    )

    save_dataframe_to_postgres(
        initial_df,
        engine,
        FEATURES_TABLE_NAME,
        ["corp_code", "stock_code", "year"],
    )
    saved_count = save_dataframe_to_postgres(
        next_df,
        engine,
        FEATURES_TABLE_NAME,
        ["corp_code", "stock_code", "year"],
    )

    saved_df = pd.read_sql(
        text(
            f"""
            SELECT corp_code, stock_code, year, revenue, created_at
            FROM {FEATURES_TABLE_NAME}
            ORDER BY corp_code ASC
            """
        ),
        engine,
    )

    assert saved_count == 2
    assert list(saved_df["corp_code"]) == ["001", "002"]
    assert list(saved_df["revenue"]) == [300, 400]
