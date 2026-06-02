from __future__ import annotations

import logging

import pandas as pd
from backend.data.db import (
    CREATED_AT_COLUMN,
    ERROR_LOG_TABLE_NAME,
    FEATURES_TABLE_NAME,
    SME_LIST_TABLE_NAME,
    create_db_engine,
)
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def normalize_key_columns(
    df: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    """비교용 키 컬럼을 null-safe 문자열로 정규화한다."""
    normalized_df = df.copy()
    for column in key_columns:
        if column in normalized_df.columns:
            normalized_df[column] = normalized_df[column].fillna("__NULL__").astype(str)
    return normalized_df


def filter_new_rows(
    df: pd.DataFrame,
    existing_df: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    """기존 테이블에 없는 신규 행만 남긴다."""
    if df.empty or existing_df.empty:
        return df

    candidate_df = normalize_key_columns(df[key_columns], key_columns)
    existing_key_df = normalize_key_columns(
        existing_df[key_columns],
        key_columns,
    ).drop_duplicates()

    merged_df = candidate_df.merge(
        existing_key_df,
        on=key_columns,
        how="left",
        indicator=True,
    )
    new_row_mask = merged_df["_merge"] == "left_only"
    return df.loc[new_row_mask].copy()


def add_created_at_column(df: pd.DataFrame, created_at: str) -> pd.DataFrame:
    """생성 시각 컬럼을 복사본 DataFrame에 추가한다."""
    updated_df = df.copy()
    updated_df[CREATED_AT_COLUMN] = created_at
    return updated_df


def save_dataframe_to_postgres(
    df: pd.DataFrame,
    engine: Engine,
    table_name: str,
    key_columns: list[str],
) -> int:
    """DataFrame을 신규 행만 골라 PostgreSQL에 저장한다."""
    if df.empty:
        logger.info("db_save_skipped table=%s reason=empty_dataframe", table_name)
        return 0

    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        df.to_sql(table_name, engine, index=False, if_exists="append")
        logger.info("db_table_created table=%s row_count=%s", table_name, len(df))
        return len(df)

    existing_query = text(f"SELECT {', '.join(key_columns)} FROM {table_name}")
    with engine.connect() as connection:
        existing_df = pd.read_sql(existing_query, connection)

    new_df = filter_new_rows(df, existing_df, key_columns)
    if new_df.empty:
        logger.info("db_save_skipped table=%s reason=no_new_rows", table_name)
        return 0

    new_df.to_sql(table_name, engine, index=False, if_exists="append")
    logger.info("db_rows_appended table=%s row_count=%s", table_name, len(new_df))
    return len(new_df)


def save_outputs_to_database(
    sme_list_df: pd.DataFrame,
    final_df: pd.DataFrame,
    error_df: pd.DataFrame,
) -> dict[str, int]:
    """기업 마스터, 재무 피처, 에러 로그를 공통 DB에 저장한다."""
    engine = create_db_engine()
    try:
        return {
            SME_LIST_TABLE_NAME: save_dataframe_to_postgres(
                sme_list_df,
                engine,
                SME_LIST_TABLE_NAME,
                ["corp_code"],
            ),
            FEATURES_TABLE_NAME: save_dataframe_to_postgres(
                final_df,
                engine,
                FEATURES_TABLE_NAME,
                ["corp_code", "stock_code", "year"],
            ),
            ERROR_LOG_TABLE_NAME: save_dataframe_to_postgres(
                error_df,
                engine,
                ERROR_LOG_TABLE_NAME,
                ["corp_code", "error_type", "message"],
            ),
        }
    finally:
        engine.dispose()
