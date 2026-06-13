from __future__ import annotations

import logging

import pandas as pd
from backend.data.db import (
    COMPANY_PROFILE_TABLE_NAME,
    CREATED_AT_COLUMN,
    ERROR_LOG_TABLE_NAME,
    FEATURES_TABLE_NAME,
    SME_LIST_TABLE_NAME,
    STATEMENT_DETAILS_TABLE_NAME,
    create_db_engine,
)
from sqlalchemy import MetaData, Table, delete, inspect, text, tuple_
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


def filter_existing_rows(
    df: pd.DataFrame,
    existing_df: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    """기존 테이블과 키가 겹치는 행만 남긴다."""
    if df.empty or existing_df.empty:
        return df.iloc[0:0].copy()

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
    existing_row_mask = merged_df["_merge"] == "both"
    return df.loc[existing_row_mask].copy()


def deduplicate_rows_by_keys(
    df: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    """동일 키가 여러 번 들어오면 마지막 행만 남긴다."""
    if df.empty:
        return df

    deduplicated_df = df.drop_duplicates(subset=key_columns, keep="last").copy()
    if len(deduplicated_df) != len(df):
        logger.info(
            "db_duplicate_keys_deduplicated row_count=%s deduplicated_row_count=%s table_keys=%s",
            len(df),
            len(deduplicated_df),
            key_columns,
        )
    return deduplicated_df.reset_index(drop=True)


def add_created_at_column(df: pd.DataFrame, created_at: str) -> pd.DataFrame:
    """생성 시각 컬럼을 복사본 DataFrame에 추가한다."""
    updated_df = df.copy()
    updated_df[CREATED_AT_COLUMN] = created_at
    return updated_df


def ensure_table_columns(
    df: pd.DataFrame,
    engine: Engine,
    table_name: str,
) -> None:
    """기존 테이블에 DataFrame 신규 컬럼이 없으면 nullable 컬럼으로 추가한다."""
    inspector = inspect(engine)
    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }
    missing_columns = [
        column
        for column in df.columns
        if column not in existing_columns
    ]
    if not missing_columns:
        return

    with engine.begin() as connection:
        for column in missing_columns:
            connection.execute(
                text(f'ALTER TABLE {table_name} ADD COLUMN "{column}" TEXT')
            )
            logger.info("db_column_added table=%s column=%s", table_name, column)


def delete_rows_by_keys(
    engine: Engine,
    table_name: str,
    key_rows_df: pd.DataFrame,
    key_columns: list[str],
) -> int:
    """주어진 키와 일치하는 기존 행을 삭제한다."""
    if key_rows_df.empty:
        return 0

    key_values = list(key_rows_df[key_columns].itertuples(index=False, name=None))
    if not key_values:
        return 0

    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    deleted_row_count = 0

    with engine.begin() as connection:
        for batch_start in range(0, len(key_values), 500):
            batch = key_values[batch_start : batch_start + 500]
            if len(key_columns) == 1:
                statement = delete(table).where(
                    table.c[key_columns[0]].in_([key_value[0] for key_value in batch])
                )
            else:
                statement = delete(table).where(
                    tuple_(*[table.c[column] for column in key_columns]).in_(batch)
                )
            result = connection.execute(statement)
            deleted_row_count += int(result.rowcount or 0)

    return deleted_row_count


def save_dataframe_to_postgres(
    df: pd.DataFrame,
    engine: Engine,
    table_name: str,
    key_columns: list[str],
) -> int:
    """DataFrame을 키 기준으로 upsert 형태로 PostgreSQL에 저장한다."""
    if df.empty:
        logger.info("db_save_skipped table=%s reason=empty_dataframe", table_name)
        return 0

    deduplicated_df = deduplicate_rows_by_keys(df, key_columns)

    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        deduplicated_df.to_sql(table_name, engine, index=False, if_exists="append")
        logger.info(
            "db_table_created table=%s row_count=%s",
            table_name,
            len(deduplicated_df),
        )
        return len(deduplicated_df)

    ensure_table_columns(deduplicated_df, engine, table_name)

    existing_query = text(f"SELECT {', '.join(key_columns)} FROM {table_name}")
    with engine.connect() as connection:
        existing_df = pd.read_sql(existing_query, connection)

    new_df = filter_new_rows(deduplicated_df, existing_df, key_columns)
    existing_rows_df = filter_existing_rows(deduplicated_df, existing_df, key_columns)

    deleted_row_count = delete_rows_by_keys(
        engine,
        table_name,
        existing_rows_df,
        key_columns,
    )
    deduplicated_df.to_sql(table_name, engine, index=False, if_exists="append")
    logger.info(
        (
            "db_rows_upserted table=%s row_count=%s inserted_count=%s "
            "updated_count=%s deleted_for_replace_count=%s"
        ),
        table_name,
        len(deduplicated_df),
        len(new_df),
        len(existing_rows_df),
        deleted_row_count,
    )
    return len(deduplicated_df)


def save_outputs_to_database(
    sme_list_df: pd.DataFrame,
    company_profile_df: pd.DataFrame,
    final_df: pd.DataFrame,
    statement_detail_df: pd.DataFrame,
    error_df: pd.DataFrame,
) -> dict[str, int]:
    """기업 마스터, 기업개황, 요약/상세 재무, 에러 로그를 공통 DB에 저장한다."""
    engine = create_db_engine()
    try:
        return {
            SME_LIST_TABLE_NAME: save_dataframe_to_postgres(
                sme_list_df,
                engine,
                SME_LIST_TABLE_NAME,
                ["corp_code"],
            ),
            COMPANY_PROFILE_TABLE_NAME: save_dataframe_to_postgres(
                company_profile_df,
                engine,
                COMPANY_PROFILE_TABLE_NAME,
                ["corp_code"],
            ),
            FEATURES_TABLE_NAME: save_dataframe_to_postgres(
                final_df,
                engine,
                FEATURES_TABLE_NAME,
                ["corp_code", "stock_code", "year"],
            ),
            STATEMENT_DETAILS_TABLE_NAME: save_dataframe_to_postgres(
                statement_detail_df,
                engine,
                STATEMENT_DETAILS_TABLE_NAME,
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
