import logging
import os
import time
import traceback
from datetime import datetime
from urllib.parse import quote_plus

import pandas as pd
from backend.backend_env import get_backend_env_path
from backend.integrations.dart_client import resolve_dart_api_key
from sqlalchemy import create_engine, inspect, text
from tqdm.auto import tqdm

try:
    import dart_fss as dart
except ModuleNotFoundError:
    dart = None

logger = logging.getLogger(__name__)

# DEFAULT 값
DEFAULT_BUSINESS_YEAR = 2024
DEFAULT_REPORT_CODE = "11011"

# 중소기업 필터링 기준
ASSET_LIMIT = 500_000_000_000
REVENUE_LIMIT = 100_000_000_000

# 사용할 재무제표 내 데이터 항목
TARGET_ACCOUNTS = [
    "매출액",
    "영업수익",
    "수익(매출액)",
    "Revenue",
    "자산총계",
    "영업이익",
    "당기순이익(손실)",
    "부채총계",
    "자본총계",
]

# 매출액 유사 단어 묶기
REVENUE_NAMES = [
    "매출액",
    "영업수익",
    "수익(매출액)",
    "Revenue",
]

DB_URL_ENV_NAME = "DATABASE_URL"
DB_HOST_ENV_NAME = "POSTGRES_HOST"
DB_PORT_ENV_NAME = "POSTGRES_PORT"
DB_USER_ENV_NAME = "POSTGRES_USER"
DB_PASSWORD_ENV_NAME = "POSTGRES_PASSWORD"
DB_NAME_ENV_NAME = "POSTGRES_DB"
SME_LIST_TABLE_NAME = "sme_list"
FEATURES_TABLE_NAME = "financial_features"
ERROR_LOG_TABLE_NAME = "financial_error_logs"
CREATED_AT_COLUMN = "created_at"


# API key 호출 함수
def resolve_api_key(args):
    return resolve_dart_api_key(args.api_key, env_path=get_env_path(args.env_file))


# SQLAlchemy DB URL 함수
def resolve_database_url():
    database_url = os.getenv(DB_URL_ENV_NAME, "").strip()
    if database_url:
        return database_url

    host = os.getenv(DB_HOST_ENV_NAME, "localhost").strip()
    port = os.getenv(DB_PORT_ENV_NAME, "5432").strip()
    user = os.getenv(DB_USER_ENV_NAME, "").strip()
    password = os.getenv(DB_PASSWORD_ENV_NAME, "").strip()
    database = os.getenv(DB_NAME_ENV_NAME, "").strip()

    if not user or not password or not database:
        raise ValueError(
            "PostgreSQL 연결 정보를 찾지 못했습니다. .env 파일에 "
            "DATABASE_URL 또는 POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB "
            "값을 설정해주세요."
        )

    quoted_password = quote_plus(password)
    return f"postgresql+psycopg2://{user}:{quoted_password}@{host}:{port}/{database}"


def create_db_engine():
    database_url = resolve_database_url()
    return create_engine(database_url)


def get_env_path(env_file):
    return get_backend_env_path(env_file)

def normalize_key_columns(df, key_columns):
    normalized_df = df.copy()
    for col in key_columns:
        if col in normalized_df.columns:
            normalized_df[col] = normalized_df[col].fillna("__NULL__").astype(str)
    return normalized_df


def filter_new_rows(df, existing_df, key_columns):
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


def add_created_at_column(df, created_at):
    updated_df = df.copy()
    updated_df[CREATED_AT_COLUMN] = created_at
    return updated_df


def save_dataframe_to_postgres(df, engine, table_name, key_columns):
    if df.empty:
        logger.info("db_save_skipped table=%s reason=empty_dataframe", table_name)
        return 0

    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        df.to_sql(table_name, engine, index=False, if_exists="append")
        logger.info("db_table_created table=%s row_count=%s", table_name, len(df))
        return len(df)

    existing_query = text(
        f"SELECT {', '.join(key_columns)} FROM {table_name}"
    )
    with engine.connect() as connection:
        existing_df = pd.read_sql(existing_query, connection)

    new_df = filter_new_rows(df, existing_df, key_columns)
    if new_df.empty:
        logger.info("db_save_skipped table=%s reason=no_new_rows", table_name)
        return 0

    new_df.to_sql(table_name, engine, index=False, if_exists="append")
    logger.info("db_rows_appended table=%s row_count=%s", table_name, len(new_df))
    return len(new_df)


def save_outputs_to_database(sme_list_df, final_df, error_df):
    engine = create_db_engine()

    saved_counts = {
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
    engine.dispose()
    return saved_counts


# 에러 로그 함수
def add_error_log(error_logs, corp_code, corp_name, error_type, message="", **kwargs):
    error_log = {
        "error_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "corp_code": corp_code,
        "corp_name": corp_name,
        "error_type": error_type,
        "message": message,
    }
    error_log.update(kwargs)
    error_logs.append(error_log)


# 기업 리스트 로드
def load_sme_candidates(sample_size: int | None = None):
    if dart is None:
        raise ModuleNotFoundError(
            (
                "dart_fss가 설치되어 있지 않습니다. "
                "`pip install dart-fss` 후 다시 실행해주세요."
            )
        )

    corp_list = dart.get_corp_list()
    if corp_list is None:
        raise RuntimeError("DART 기업 목록을 불러오지 못했습니다.")

    corp_data = [corp.to_dict() for corp in corp_list.corps]
    df = pd.DataFrame(corp_data)

    required_columns = {"corp_code", "corp_name", "stock_code", "corp_cls"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise KeyError(f"기업 목록에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")

    # KOSDAQ, KONEX 기업만 추출
    sme_df = df[df["corp_cls"].isin(["K", "N"])].copy().reset_index(drop=True)

    if sample_size is not None:
        sme_df = sme_df.head(sample_size).reset_index(drop=True)

    return df, sme_df


# 숫자형 변환 위해 금액 데이터 전처리 함수
def to_numeric_series(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .replace("-", "0")
        .replace("", "0"),
        errors="coerce",
    )


# 숫자형 컬럼 숫자형 변환 함수
def convert_amount_columns(filtered_df, amount_cols):
    converted_df = filtered_df.copy()
    for col in amount_cols:
        converted_df[col] = to_numeric_series(converted_df[col]).to_numpy()
    return converted_df


# 연결제무제표 사용 함수
def select_preferred_financial_statement(filtered_df):
    cfs_df = filtered_df[filtered_df["fs_div"] == "CFS"].copy()
    if not cfs_df.empty:
        return cfs_df

    ofs_df = filtered_df[filtered_df["fs_div"] == "OFS"].copy()
    if not ofs_df.empty:
        return ofs_df

    return pd.DataFrame()


# 연도 맵핑 함수
def get_year_mapping(business_year):
    return {
        "thstrm_amount": business_year,
        "frmtrm_amount": business_year - 1,
        "bfefrmtrm_amount": business_year - 2,
    }


# 회사 재무 데이터 조회 함수
def process_company(row, business_year, report_code, error_logs):
    if dart is None:
        raise ModuleNotFoundError(
            (
                "dart_fss가 설치되어 있지 않습니다. "
                "`pip install dart-fss` 후 다시 실행해주세요."
            )
        )

    corp_code = row["corp_code"]
    corp_name = row["corp_name"]

    try:
        data = dart.api.finance.fnltt_singl_acnt(
            corp_code=corp_code,
            bsns_year=str(business_year),
            reprt_code=report_code,
        )

        if "list" not in data:
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="NO_LIST",
                message="API 응답에 list 없음",
                response=data,
            )
            return {"status": "error", "records": []}

        temp_df = pd.DataFrame(data["list"])
        if temp_df.empty:
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="EMPTY_DF",
                message="재무 데이터 없음",
            )
            return {"status": "error", "records": []}

        filtered_df = temp_df[temp_df["account_nm"].isin(TARGET_ACCOUNTS)][
            [
                "corp_code",
                "stock_code",
                "fs_div",
                "account_nm",
                "thstrm_amount",
                "frmtrm_amount",
                "bfefrmtrm_amount",
            ]
        ].copy()

        filtered_df = select_preferred_financial_statement(filtered_df)
        if filtered_df.empty:
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="NO_FS",
                message="사용 가능한 재무제표 없음",
            )
            return {"status": "error", "records": []}

        amount_cols = ["thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount"]
        filtered_df = convert_amount_columns(filtered_df, amount_cols)

        asset_row = filtered_df[filtered_df["account_nm"] == "자산총계"]
        if asset_row.empty:
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="NO_ASSET",
                message="자산총계 없음",
            )
            return {"status": "error", "records": []}

        total_assets = asset_row.iloc[0]["thstrm_amount"]
        if pd.isna(total_assets):
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="ASSET_NAN",
                message="자산총계 숫자 변환 실패",
            )
            return {"status": "error", "records": []}

        # 1차 필터링: 자산총액 기준
        if total_assets > ASSET_LIMIT:
            return {"status": "asset_filtered", "records": []}

        liability_row = filtered_df[filtered_df["account_nm"] == "부채총계"]
        if liability_row.empty:
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="NO_LIABILITY",
                message="부채총계 없음",
            )
            return {"status": "error", "records": []}

        total_liabilities = liability_row.iloc[0]["thstrm_amount"]
        if pd.isna(total_liabilities):
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="LIABILITY_NAN",
                message="부채총계 숫자 변환 실패",
            )
            return {"status": "error", "records": []}

        revenue_row = filtered_df[filtered_df["account_nm"].isin(REVENUE_NAMES)]
        if revenue_row.empty:
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="NO_REVENUE",
                message="매출 관련 계정 없음",
            )
            return {"status": "error", "records": []}

        revenue_row = revenue_row.iloc[0]
        avg_revenue_last_3y = round(
            (
                revenue_row["thstrm_amount"]
                + revenue_row["frmtrm_amount"]
                + revenue_row["bfefrmtrm_amount"]
            )
            / 3,
            1,
        )
        if pd.isna(avg_revenue_last_3y):
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="REVENUE_NAN",
                message="평균 매출 계산 실패",
            )
            return {"status": "error", "records": []}

        # 2차 필터링: 3년 평균 매출액 기준
        if avg_revenue_last_3y > REVENUE_LIMIT:
            return {"status": "revenue_filtered", "records": []}

        year_mapping = get_year_mapping(business_year)
        records = []
        for _, account_row in filtered_df.iterrows():
            for amount_col, year in year_mapping.items():
                records.append(
                    {
                        "corp_code": corp_code,
                        "corp_name": corp_name,
                        "stock_code": account_row["stock_code"],
                        "year": year,
                        "account_nm": account_row["account_nm"],
                        "amount": account_row[amount_col],
                        "avg_revenue_last_3y": avg_revenue_last_3y,
                        "total_assets": total_assets,
                    }
                )

        return {"status": "success", "records": records}

    except Exception as exc:
        add_error_log(
            error_logs,
            corp_code=corp_code,
            corp_name=corp_name,
            error_type="EXCEPTION",
            message=str(exc),
            traceback=traceback.format_exc(),
        )
        return {"status": "error", "records": []}


# 진행 상황 확인 위한 함수
def run_collection(sme_df, business_year, report_code):
    processed_records = []
    error_logs = []
    success_count = 0
    asset_filtered_count = 0
    revenue_filtered_count = 0
    error_count = 0
    start_time = time.time()
    progress_bar = tqdm(sme_df.iterrows(), total=len(sme_df))
    for idx, (_, row) in enumerate(progress_bar):
        result = process_company(row, business_year, report_code, error_logs)
        status = result["status"]

        if status == "success":
            processed_records.extend(result["records"])
            success_count += 1
        elif status == "asset_filtered":
            asset_filtered_count += 1
        elif status == "revenue_filtered":
            revenue_filtered_count += 1
        else:
            error_count += 1

        if idx % 50 == 0:
            elapsed = round(time.time() - start_time, 1)
            progress_bar.set_postfix(
                {
                    "success": success_count,
                    "asset_filtered": asset_filtered_count,
                    "revenue_filtered": revenue_filtered_count,
                    "error": error_count,
                    "elapsed_s": elapsed,
                },
                refresh=False,
            )

    stats = {
        "success_count": success_count,
        "asset_filtered_count": asset_filtered_count,
        "revenue_filtered_count": revenue_filtered_count,
        "error_count": error_count,
        "elapsed_total": round(time.time() - start_time, 1),
    }
    return processed_records, error_logs, stats


# 최종 데이터프레임 만드는 함수
def build_final_dataframe(processed_records):
    final_columns = [
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
        CREATED_AT_COLUMN,
    ]

    if not processed_records:
        return pd.DataFrame(columns=final_columns)

    long_df = pd.DataFrame(processed_records)
    final_df = long_df.pivot_table(
        index=[
            "corp_code",
            "corp_name",
            "stock_code",
            "year",
            "avg_revenue_last_3y",
            "total_assets",
        ],
        columns="account_nm",
        values="amount",
        aggfunc="first",
    ).reset_index()
    final_df.columns.name = None

    revenue_source_columns = [col for col in REVENUE_NAMES if col in final_df.columns]
    if revenue_source_columns:
        final_df["revenue"] = final_df[revenue_source_columns].bfill(axis=1).iloc[:, 0]

    column_mapping = {
        "영업이익": "operating_income",
        "당기순이익(손실)": "net_income",
        "자산총계": "total_assets_statement",
        "부채총계": "total_liabilities",
        "자본총계": "total_equity",
    }
    final_df = final_df.rename(columns=column_mapping)

    existing_columns = [col for col in final_columns if col in final_df.columns]
    return final_df[existing_columns]


# 중소기업 리스트 데이터프레임 만드는 함수
def build_sme_list_dataframe(final_df):
    columns = [
        "corp_code",
        "corp_name",
        "stock_code",
        "avg_revenue_last_3y",
        "total_assets",
        CREATED_AT_COLUMN,
    ]
    if final_df.empty:
        return pd.DataFrame(columns=columns)

    existing_columns = [col for col in columns if col in final_df.columns]
    return final_df[existing_columns].drop_duplicates().reset_index(drop=True)


# api 호출 없이 self test 함수
def run_self_tests():
    numeric_input = pd.Series(["1,000", "-", "", "2500", None])
    numeric_output = to_numeric_series(numeric_input)
    assert numeric_output.iloc[0] == 1000
    assert numeric_output.iloc[1] == 0
    assert numeric_output.iloc[2] == 0
    assert numeric_output.iloc[3] == 2500
    assert pd.isna(numeric_output.iloc[4])

    amount_df = pd.DataFrame(
        {
            "thstrm_amount": pd.Series(["1,000", "-"], dtype="string"),
            "frmtrm_amount": pd.Series(["900", "100"], dtype="string"),
            "bfefrmtrm_amount": pd.Series(["800", ""], dtype="string"),
        }
    )
    converted_df = convert_amount_columns(
        amount_df,
        ["thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount"],
    )
    assert converted_df["thstrm_amount"].iloc[0] == 1000
    assert converted_df["thstrm_amount"].iloc[1] == 0
    assert converted_df["bfefrmtrm_amount"].iloc[1] == 0

    sample_records = [
        {
            "corp_code": "001",
            "corp_name": "테스트기업",
            "stock_code": "123456",
            "year": 2024,
            "account_nm": "매출액",
            "amount": 100,
            "avg_revenue_last_3y": 90.0,
            "total_assets": 1000,
        },
        {
            "corp_code": "001",
            "corp_name": "테스트기업",
            "stock_code": "123456",
            "year": 2024,
            "account_nm": "영업이익",
            "amount": 20,
            "avg_revenue_last_3y": 90.0,
            "total_assets": 1000,
        },
        {
            "corp_code": "001",
            "corp_name": "테스트기업",
            "stock_code": "123456",
            "year": 2023,
            "account_nm": "매출액",
            "amount": 90,
            "avg_revenue_last_3y": 90.0,
            "total_assets": 1000,
        },
    ]
    final_df = build_final_dataframe(sample_records)
    assert not final_df.empty
    assert "revenue" in final_df.columns
    assert "operating_income" in final_df.columns

    sme_list_df = build_sme_list_dataframe(final_df)
    assert len(sme_list_df) == 1
    assert sme_list_df.iloc[0]["corp_code"] == "001"

    empty_df = build_final_dataframe([])
    assert empty_df.empty

    created_df = add_created_at_column(final_df, "2026-05-20")
    assert CREATED_AT_COLUMN in created_df.columns
    assert created_df.iloc[0][CREATED_AT_COLUMN] == "2026-05-20"

    current_df = pd.DataFrame(
        [
            {"corp_code": "001", "stock_code": "111111", "year": 2024, "value": 1},
            {"corp_code": "002", "stock_code": "222222", "year": 2024, "value": 2},
        ]
    )
    existing_df = pd.DataFrame(
        [
            {"corp_code": "001", "stock_code": "111111", "year": 2024},
        ]
    )
    filtered_df = filter_new_rows(
        current_df,
        existing_df,
        ["corp_code", "stock_code", "year"],
    )
    assert len(filtered_df) == 1
    assert filtered_df.iloc[0]["corp_code"] == "002"

    news_result = execute_news_pipeline(
        company_name="테스트기업",
        year=2024,
        output_dir=".",
    )
    assert news_result["status"] == "not_configured"
    assert news_result["article_count"] == 0

    logger.info("collector_self_tests_passed")


def execute_dart_pipeline(
    year: int,
    sample_size: int | None = None,
    skip_db_save: bool = False,
):
    if dart is None:
        raise ModuleNotFoundError("dart_fss가 설치되어 있지 않습니다.")

    class DummyArgs:
        api_key: str | None = None
        env_file: str | None = None

    api_key = resolve_api_key(DummyArgs())
    dart.set_api_key(api_key=api_key)

    _, sme_df = load_sme_candidates(sample_size=sample_size)

    processed_records, error_logs, stats = run_collection(
        sme_df=sme_df,
        business_year=year,
        report_code=DEFAULT_REPORT_CODE,
    )

    created_at = datetime.now().strftime("%Y-%m-%d")
    final_df = build_final_dataframe(processed_records)
    final_df = add_created_at_column(final_df, created_at)
    sme_list_df = build_sme_list_dataframe(final_df)
    error_df = pd.DataFrame(error_logs)

    db_save_counts = {}
    if not skip_db_save:
        db_save_counts = save_outputs_to_database(sme_list_df, final_df, error_df)

    return {
        "status": "success",
        "stats": stats,
        "sme_count": len(sme_list_df),
        "financial_data_count": len(final_df),
        "db_save_counts": db_save_counts,
        "source": "dart",
    }


def execute_news_pipeline(
    *,
    company_name: str | None,
    year: int,
    output_dir: str,
) -> dict:
    """뉴스 수집 파이프라인 placeholder.

    실제 뉴스 수집 로직이 추가되기 전까지는 구조만 고정해 반환한다.
    """
    logger.info(
        "news_pipeline_requested company_name=%s year=%s output_dir=%s",
        company_name,
        year,
        output_dir,
    )
    return {
        "status": "not_configured",
        "source": "news",
        "article_count": 0,
        "items": [],
        "message": "뉴스 수집 파이프라인은 아직 구현되지 않았습니다.",
    }
