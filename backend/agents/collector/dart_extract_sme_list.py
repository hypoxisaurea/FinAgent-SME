import argparse
import time
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
from tqdm.auto import tqdm

try:
    import dart_fss as dart
except ModuleNotFoundError:
    dart = None


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

# 결과 저장 파일 이름
SME_LIST_FILENAME = "sme_list.csv"
FEATURES_FILENAME = "financial_features.csv"
ERROR_LOG_FILENAME = "financial_error_logs.csv"
TEMP_FILENAME = "temp_processed_records.csv"


# 커맨드 라인 인수 함수 
def parse_args():
    parser = argparse.ArgumentParser(
        description="DART에서 중소기업 후보 목록과 재무 데이터를 추출합니다."
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="DART Open API 키. 생략하면 실행 중 입력받습니다.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=DEFAULT_BUSINESS_YEAR,
        help=f"사업연도. 기본값: {DEFAULT_BUSINESS_YEAR}",
    )
    parser.add_argument(
        "--report-code",
        default=DEFAULT_REPORT_CODE,
        help=f"보고서 코드. 기본값: {DEFAULT_REPORT_CODE}",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="결과 CSV 저장 디렉터리. 기본값: 현재 폴더",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="테스트용 샘플 기업 수. 지정하면 앞에서부터 일부만 실행합니다.",
    )
    parser.add_argument(
        "--run-self-test",
        action="store_true",
        help="API 호출 없이 helper 함수 self test만 실행합니다.",
    )
    return parser.parse_args()


# API key 호출 함수
def resolve_api_key(args):
    if args.api_key and args.api_key.strip():
        return args.api_key.strip()

    api_key = input("DART API KEY를 입력하세요: ").strip()
    if not api_key:
        raise ValueError("API 키가 비어 있습니다. --api-key 또는 입력값을 제공해주세요.")
    return api_key


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
def load_sme_candidates(sample_size=None):
    if dart is None:
        raise ModuleNotFoundError(
            "dart_fss가 설치되어 있지 않습니다. `pip install dart-fss` 후 다시 실행해주세요."
        )

    corp_list = dart.get_corp_list()
    corp_data = [corp.to_dict() for corp in corp_list.corps]
    df = pd.DataFrame(corp_data)

    required_columns = {"corp_code", "corp_name", "stock_code", "corp_cls"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise KeyError(f"기업 목록에 필요한 컬럼이 없습니다: {sorted(missing_columns)}")

    sme_df = df[df["corp_cls"].isin(["K", "N"])].copy().reset_index(drop=True)      # KOSDAQ, KONEX 기업만 추출

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
            "dart_fss가 설치되어 있지 않습니다. `pip install dart-fss` 후 다시 실행해주세요."
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
def run_collection(sme_df, business_year, report_code, temp_save_path):
    temp_save_path = Path(temp_save_path)
    temp_save_path.parent.mkdir(parents=True, exist_ok=True)

    processed_records = []
    error_logs = []
    success_count = 0
    asset_filtered_count = 0
    revenue_filtered_count = 0
    error_count = 0
    start_time = time.time()

    for idx, (_, row) in enumerate(tqdm(sme_df.iterrows(), total=len(sme_df))):
        if idx % 50 == 0:
            elapsed = round(time.time() - start_time, 1)
            print(
                f"\n[{idx}/{len(sme_df)}] 진행중 | "
                f"성공: {success_count} | "
                f"자산필터제외: {asset_filtered_count} | "
                f"매출필터제외: {revenue_filtered_count} | "
                f"에러: {error_count} | "
                f"경과시간: {elapsed}초"
            )

        result = process_company(row, business_year, report_code, error_logs)
        status = result["status"]

        if status == "success":
            processed_records.extend(result["records"])
            success_count += 1

            if success_count % 500 == 0 and processed_records:
                pd.DataFrame(processed_records).to_csv(
                    temp_save_path,
                    index=False,
                    encoding="utf-8-sig",
                )
                print(f"\n중간 저장 완료 | 성공 기업 수: {success_count}")
        elif status == "asset_filtered":
            asset_filtered_count += 1
        elif status == "revenue_filtered":
            revenue_filtered_count += 1
        else:
            error_count += 1

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
    ]
    if final_df.empty:
        return pd.DataFrame(columns=columns)

    existing_columns = [col for col in columns if col in final_df.columns]
    return final_df[existing_columns].drop_duplicates().reset_index(drop=True)


# 결과 저장 함수
def save_outputs(sme_list_df, final_df, error_df, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sme_list_path = output_dir / SME_LIST_FILENAME
    features_path = output_dir / FEATURES_FILENAME
    error_log_path = output_dir / ERROR_LOG_FILENAME

    sme_list_df.to_csv(sme_list_path, index=False, encoding="utf-8-sig")
    final_df.to_csv(features_path, index=False, encoding="utf-8-sig")
    error_df.to_csv(error_log_path, index=False, encoding="utf-8-sig")

    print(f"저장 완료: {sme_list_path}")
    print(f"저장 완료: {features_path}")
    print(f"저장 완료: {error_log_path}")


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

    print("Self tests passed.")


def main():
    args = parse_args()

    if args.run_self_test:
        run_self_tests()
        return

    if dart is None:
        raise ModuleNotFoundError(
            "dart_fss가 설치되어 있지 않습니다. `pip install dart-fss` 후 다시 실행해주세요."
        )

    start_time = time.time()
    api_key = resolve_api_key(args)
    dart.set_api_key(api_key=api_key)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_save_path = output_dir / TEMP_FILENAME

    print("DART 기업 목록 조회 시작...")
    all_corp_df, sme_df = load_sme_candidates(sample_size=args.sample_size)
    print(f"전체 기업 수: {len(all_corp_df)}")
    print(f"중소기업 후보 수(K, N): {len(sme_df)}")

    processed_records, error_logs, stats = run_collection(
        sme_df=sme_df,
        business_year=args.year,
        report_code=args.report_code,
        temp_save_path=temp_save_path,
    )

    final_df = build_final_dataframe(processed_records)
    sme_list_df = build_sme_list_dataframe(final_df)
    error_df = pd.DataFrame(error_logs)

    save_outputs(
        sme_list_df=sme_list_df,
        final_df=final_df,
        error_df=error_df,
        output_dir=output_dir,
    )

    elapsed_total = round(time.time() - start_time, 1)
    print("\n==========================")
    print("처리 완료")
    print("==========================")
    print(f"성공 기업 수: {stats['success_count']}")
    print(f"자산 필터 제외: {stats['asset_filtered_count']}")
    print(f"매출 필터 제외: {stats['revenue_filtered_count']}")
    print(f"에러 수: {stats['error_count']}")
    print(f"최종 SME 목록 수: {len(sme_list_df)}")
    print(f"최종 재무 데이터 수: {len(final_df)}")
    print(f"총 소요시간: {elapsed_total}초")


if __name__ == "__main__":
    main()
