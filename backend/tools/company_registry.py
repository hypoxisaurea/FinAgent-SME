import logging
import time
import traceback
from datetime import datetime
from typing import Any

import pandas as pd
from backend import backend_env
from backend.data.db import (
    CREATED_AT_COLUMN,
)
from backend.data.db import (
    create_db_engine as infrastructure_create_db_engine,
)
from backend.data.db import (
    resolve_database_url as infrastructure_resolve_database_url,
)
from backend.data.repositories.company_registry import (
    add_created_at_column,
    filter_new_rows,
)
from backend.integrations.dart_client import get_dart_json, resolve_dart_api_key
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

STATEMENT_DETAIL_ACCOUNT_MAP = {
    "current_assets": ["유동자산"],
    "current_liabilities": ["유동부채"],
    "total_assets_statement": ["자산총계"],
    "total_liabilities": ["부채총계"],
    "total_equity": ["자본총계"],
    "retained_earnings": ["이익잉여금", "이익잉여금(결손금)"],
    "inventory": ["재고자산"],
    "accounts_receivable": [
        "매출채권",
        "매출채권 및 기타채권",
        "매출채권및기타채권",
    ],
    "accounts_payable": [
        "매입채무",
        "매입채무 및 기타채무",
        "매입채무및기타채무",
    ],
    "short_term_borrowings": ["단기차입금", "단기차입부채"],
    "current_portion_long_term_borrowings": [
        "유동성장기차입금",
        "유동성성장기차입부채",
        "유동성장기차입부채",
    ],
    "long_term_borrowings": ["장기차입금", "장기차입부채"],
    "bonds": ["사채"],
    "tangible_assets": ["유형자산"],
    "revenue": ["매출액", "영업수익", "수익(매출액)", "Revenue"],
    "cost_of_goods_sold": ["매출원가", "영업비용"],
    "operating_income": ["영업이익", "영업이익(손실)"],
    "net_income": ["당기순이익(손실)", "당기순이익"],
    "interest_expense": ["금융비용", "이자비용"],
    "operating_cashflow": ["영업활동현금흐름", "영업활동 현금흐름"],
    "capital_expenditure": ["유형자산의 취득", "유형자산취득"],
}

STATEMENT_DETAIL_COLUMNS = [
    "corp_code",
    "corp_name",
    "stock_code",
    "year",
    "avg_revenue_last_3y",
    "current_assets",
    "current_liabilities",
    "total_assets_statement",
    "total_liabilities",
    "total_equity",
    "retained_earnings",
    "inventory",
    "accounts_receivable",
    "accounts_payable",
    "short_term_borrowings",
    "current_portion_long_term_borrowings",
    "long_term_borrowings",
    "bonds",
    "tangible_assets",
    "revenue",
    "cost_of_goods_sold",
    "operating_income",
    "net_income",
    "interest_expense",
    "operating_cashflow",
    "capital_expenditure",
    "audit_opinion",
    "is_external_audit",
    CREATED_AT_COLUMN,
]

STATEMENT_DETAIL_ACCOUNT_NAMES = sorted(
    {
        account_name
        for account_names in STATEMENT_DETAIL_ACCOUNT_MAP.values()
        for account_name in account_names
    }
)

COMPANY_PROFILE_COLUMNS = [
    "corp_cls",
    "stock_name",
    "ceo_name",
    "address",
    "homepage_url",
    "ir_url",
    "phone_number",
    "fax_number",
    "industry_code",
    "established_date",
    "settlement_month",
]

# 매출액 유사 단어 묶기
REVENUE_NAMES = [
    "매출액",
    "영업수익",
    "수익(매출액)",
    "Revenue",
]

# API key 호출 함수
def resolve_api_key(args):
    return resolve_dart_api_key(args.api_key, env_path=get_env_path(args.env_file))


def resolve_database_url() -> str:
    """기존 호출 호환을 위해 DB URL 해석 함수를 노출한다."""
    return infrastructure_resolve_database_url()


def create_db_engine():
    """기존 호출 호환을 위해 공통 DB 엔진 팩토리를 노출한다."""
    return infrastructure_create_db_engine()


def get_env_path(env_file):
    """기존 호출 호환을 위해 백엔드 env 경로 해석 함수를 노출한다."""
    return backend_env.get_backend_env_path(env_file)


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


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_established_date(value: Any) -> str | None:
    text = normalize_text(value)
    if text is None:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 8:
        return text
    try:
        return datetime.strptime(digits, "%Y%m%d").date().isoformat()
    except ValueError:
        return text


def fetch_company_profile(corp_code: str) -> dict[str, Any]:
    payload = get_dart_json(
        "company.json",
        params={"corp_code": str(corp_code).zfill(8)},
        timeout=10,
    )
    if payload.get("status") != "000":
        raise ValueError(f"기업개황 조회 실패: {payload.get('message')}")

    return {
        "corp_code": str(payload.get("corp_code") or corp_code).zfill(8),
        "corp_cls": normalize_text(payload.get("corp_cls")),
        "stock_name": normalize_text(payload.get("stock_name")),
        "stock_code": normalize_text(payload.get("stock_code")),
        "ceo_name": normalize_text(payload.get("ceo_nm")),
        "address": normalize_text(payload.get("adres")),
        "homepage_url": normalize_text(payload.get("hm_url")),
        "ir_url": normalize_text(payload.get("ir_url")),
        "phone_number": normalize_text(payload.get("phn_no")),
        "fax_number": normalize_text(payload.get("fax_no")),
        "industry_code": normalize_text(payload.get("induty_code")),
        "established_date": normalize_established_date(payload.get("est_dt")),
        "settlement_month": normalize_text(payload.get("acc_mt")),
    }


def build_company_profile_dataframe(
    sme_list_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, int]]:
    columns = ["corp_code", *COMPANY_PROFILE_COLUMNS]
    if sme_list_df.empty:
        return pd.DataFrame(columns=columns), [], {
            "profile_success_count": 0,
            "profile_error_count": 0,
        }

    profile_records: list[dict[str, Any]] = []
    error_logs: list[dict[str, Any]] = []
    unique_companies = (
        sme_list_df[["corp_code", "corp_name"]]
        .drop_duplicates(subset=["corp_code"])
        .reset_index(drop=True)
    )

    for _, row in tqdm(
        unique_companies.iterrows(),
        total=len(unique_companies),
        desc="기업개황 수집",
    ):
        corp_code = str(row["corp_code"]).zfill(8)
        corp_name = row.get("corp_name")
        try:
            profile_records.append(fetch_company_profile(corp_code))
        except Exception as exc:  # noqa: BLE001
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="COMPANY_PROFILE_ERROR",
                message=str(exc),
            )

    return (
        pd.DataFrame(profile_records, columns=columns),
        error_logs,
        {
            "profile_success_count": len(profile_records),
            "profile_error_count": len(error_logs),
        },
    )


def fetch_audit_metadata(corp_code: str, business_year: int) -> tuple[str | None, bool]:
    """기준 사업연도의 감사의견과 외감 여부를 조회한다."""
    try:
        payload = get_dart_json(
            "accnutAdtorNmNdAdtOpinion.json",
            params={
                "corp_code": str(corp_code).zfill(8),
                "bsns_year": str(business_year),
                "reprt_code": DEFAULT_REPORT_CODE,
            },
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "audit_metadata_fetch_failed corp_code=%s year=%s error=%s",
            corp_code,
            business_year,
            exc,
        )
        return None, False

    if payload.get("status") != "000":
        return None, False

    items = payload.get("list", [])
    if not items:
        return None, False

    target = next(
        (item for item in items if "당기" in str(item.get("bsns_year", ""))),
        items[0],
    )
    opinion = normalize_text(target.get("adt_opinion"))
    if opinion == "-":
        opinion = None
    return opinion, True


# 연결제무제표 사용 함수
def select_preferred_financial_statement(filtered_df):
    cfs_df = filtered_df[filtered_df["fs_div"] == "CFS"].copy()
    if not cfs_df.empty:
        return cfs_df

    ofs_df = filtered_df[filtered_df["fs_div"] == "OFS"].copy()
    if not ofs_df.empty:
        return ofs_df

    return pd.DataFrame()


def build_account_subset_dataframe(
    raw_df: pd.DataFrame,
    target_accounts: list[str],
) -> pd.DataFrame:
    columns = [
        "corp_code",
        "stock_code",
        "fs_div",
        "account_nm",
        "thstrm_amount",
        "frmtrm_amount",
        "bfefrmtrm_amount",
    ]
    subset_df = raw_df[raw_df["account_nm"].isin(target_accounts)][columns].copy()
    if subset_df.empty:
        return subset_df

    subset_df = select_preferred_financial_statement(subset_df)
    if subset_df.empty:
        return subset_df

    return convert_amount_columns(
        subset_df,
        ["thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount"],
    )


def normalize_account_name(value: Any) -> str:
    return "".join(str(value or "").split())


def extract_account_amount(
    statement_df: pd.DataFrame,
    amount_column: str,
    candidate_names: list[str],
) -> float | None:
    if statement_df.empty:
        return None

    normalized_candidates = {
        normalize_account_name(candidate_name)
        for candidate_name in candidate_names
    }
    matched_rows = statement_df[
        statement_df["account_nm"].map(normalize_account_name).isin(
            normalized_candidates
        )
    ]
    if matched_rows.empty:
        return None

    value = matched_rows.iloc[0][amount_column]
    if pd.isna(value):
        return None
    return float(value)


def build_statement_detail_records(
    statement_df: pd.DataFrame,
    *,
    corp_code: str,
    corp_name: str,
    stock_code: str | None,
    business_year: int,
    avg_revenue_last_3y: float,
    audit_opinion: str | None,
    is_external_audit: bool,
) -> list[dict[str, Any]]:
    """단일 기업의 재무제표 DataFrame에서 연도별 상세 재무 스냅샷을 만든다."""
    if statement_df.empty:
        return []

    year_mapping = get_year_mapping(business_year)
    records: list[dict[str, Any]] = []
    normalized_stock_code = normalize_text(stock_code)

    for amount_column, year in year_mapping.items():
        record: dict[str, Any] = {
            "corp_code": corp_code,
            "corp_name": corp_name,
            "stock_code": normalized_stock_code,
            "year": year,
            "avg_revenue_last_3y": avg_revenue_last_3y,
            "audit_opinion": audit_opinion if year == business_year else None,
            "is_external_audit": bool(is_external_audit) if year == business_year else False,
        }

        for column_name, candidate_names in STATEMENT_DETAIL_ACCOUNT_MAP.items():
            value = extract_account_amount(statement_df, amount_column, candidate_names)
            if column_name == "capital_expenditure" and value is not None:
                value = abs(value)
            record[column_name] = value

        records.append(record)

    return records


def build_statement_detail_dataframe(statement_records: list[dict[str, Any]]) -> pd.DataFrame:
    """연도별 상세 재무 스냅샷 레코드를 DataFrame으로 정규화한다."""
    if not statement_records:
        return pd.DataFrame(columns=STATEMENT_DETAIL_COLUMNS)
    return pd.DataFrame(statement_records, columns=STATEMENT_DETAIL_COLUMNS)


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

        filtered_df = build_account_subset_dataframe(temp_df, TARGET_ACCOUNTS)
        if filtered_df.empty:
            add_error_log(
                error_logs,
                corp_code=corp_code,
                corp_name=corp_name,
                error_type="NO_FS",
                message="사용 가능한 재무제표 없음",
            )
            return {"status": "error", "records": []}

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
        detail_df = build_account_subset_dataframe(
            temp_df,
            STATEMENT_DETAIL_ACCOUNT_NAMES,
        )
        audit_opinion, is_external_audit = fetch_audit_metadata(
            corp_code,
            business_year,
        )
        statement_records = build_statement_detail_records(
            detail_df,
            corp_code=corp_code,
            corp_name=corp_name,
            stock_code=normalize_text(row.get("stock_code")) or normalize_text(
                revenue_row.get("stock_code")
            ),
            business_year=business_year,
            avg_revenue_last_3y=avg_revenue_last_3y,
            audit_opinion=audit_opinion,
            is_external_audit=is_external_audit,
        )

        return {
            "status": "success",
            "records": records,
            "statement_records": statement_records,
        }

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
    statement_records = []
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
            statement_records.extend(result.get("statement_records", []))
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
    return processed_records, statement_records, error_logs, stats


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

    statement_records = [
        {
            "corp_code": "001",
            "corp_name": "테스트기업",
            "stock_code": "123456",
            "year": 2024,
            "avg_revenue_last_3y": 90.0,
            "current_assets": 10,
            "current_liabilities": 5,
            "total_assets_statement": 1000,
            "total_liabilities": 300,
            "total_equity": 700,
            "retained_earnings": 100,
            "inventory": 20,
            "accounts_receivable": 30,
            "accounts_payable": 15,
            "short_term_borrowings": 40,
            "current_portion_long_term_borrowings": 10,
            "long_term_borrowings": 50,
            "bonds": 0,
            "tangible_assets": 200,
            "revenue": 100,
            "cost_of_goods_sold": 60,
            "operating_income": 20,
            "net_income": 10,
            "interest_expense": 3,
            "operating_cashflow": 15,
            "capital_expenditure": 5,
            "audit_opinion": "적정",
            "is_external_audit": True,
        }
    ]
    statement_detail_df = build_statement_detail_dataframe(statement_records)
    assert not statement_detail_df.empty
    assert "current_assets" in statement_detail_df.columns
    assert "capital_expenditure" in statement_detail_df.columns

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
) -> dict[str, Any]:
    """기존 import 호환을 위한 서비스 래퍼."""
    from backend.data.services.company_registry_pipeline import (
        execute_dart_pipeline as execute_dart_pipeline_service,
    )

    return execute_dart_pipeline_service(
        year=year,
        sample_size=sample_size,
        skip_db_save=skip_db_save,
    )


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
