import argparse
import csv
import io
import logging
import os
import re
import zipfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from backend_env import get_backend_env_path, load_backend_env

logger = logging.getLogger(__name__)

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"

DEFAULT_BGN_DE = "20240101"
DEFAULT_END_DE = "20241231"


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", str(name))


def resolve_api_key(args=None, env_path=None):
    if args is not None and getattr(args, "api_key", None):
        return args.api_key.strip()

    load_backend_env(override=True, env_path=env_path)
    api_key = os.getenv("OPEN_DART_API_KEY", "").strip()
    if api_key:
        return api_key

    candidate_path = get_backend_env_path(env_path)

    raise ValueError(
        "OPEN_DART_API_KEY가 없습니다. "
        f"{candidate_path} 또는 환경 변수에 값을 설정해주세요."
    )


def load_corp_codes_from_csv(csv_path, corp_code_column="corp_code"):
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {csv_path}")

    encodings = ["utf-8-sig", "utf-8", "euc-kr", "cp949"]

    for encoding in encodings:
        try:
            with csv_path.open(newline="", encoding=encoding) as csvfile:
                reader = csv.DictReader(csvfile)

                if reader.fieldnames is None:
                    raise ValueError("CSV 파일에 헤더가 없습니다.")

                normalized = [
                    field.strip().lstrip("\ufeff")
                    for field in reader.fieldnames
                ]

                fieldname_map = dict(zip(normalized, reader.fieldnames))

                if corp_code_column not in fieldname_map:
                    raise KeyError(
                        f"CSV 파일에 '{corp_code_column}' 컬럼이 없습니다."
                    )

                actual_column = fieldname_map[corp_code_column]

                return [
                    row[actual_column].strip()
                    for row in reader
                    if row.get(actual_column)
                    and row[actual_column].strip()
                ]

        except (UnicodeDecodeError, KeyError, ValueError):
            continue

    raise ValueError(
        "지원되는 인코딩으로 CSV 파일을 읽을 수 없습니다."
    )


def fetch_opendart_list_records(
    api_key,
    corp_code,
    bgn_de=DEFAULT_BGN_DE,
    end_de=DEFAULT_END_DE,
    page_count=100,
    timeout=30,
):
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_count": page_count,
    }

    response = requests.get(DART_LIST_URL, params=params, timeout=timeout)
    response.raise_for_status()

    data = response.json()

    if data.get("status") != "000":
        raise ValueError(
            f"DART 공시 목록 조회 실패: {data.get('message')}"
        )

    return data.get("list", [])


def select_target_report(reports):
    if not reports:
        raise ValueError("공시 목록이 비어 있습니다.")

    audit_reports = [
        report for report in reports
        if "감사보고서" in report.get("report_nm", "")
    ]

    return audit_reports[0] if audit_reports else reports[0]


def get_latest_rcept_no(
    api_key,
    corp_code,
    bgn_de=DEFAULT_BGN_DE,
    end_de=DEFAULT_END_DE,
):
    reports = fetch_opendart_list_records(
        api_key=api_key,
        corp_code=corp_code,
        bgn_de=bgn_de,
        end_de=end_de,
    )

    if not reports:
        raise ValueError(f"{corp_code} 기업의 공시 목록을 찾을 수 없습니다.")

    target_report = select_target_report(reports)

    logger.info("선택된 공시: %s", target_report.get("report_nm"))
    logger.info("기업명: %s", target_report.get("corp_name"))
    logger.info("rcept_no: %s", target_report.get("rcept_no"))

    return target_report["rcept_no"], target_report["corp_name"]


def fetch_document_zip(api_key, rcept_no, timeout=30):
    params = {
        "crtfc_key": api_key,
        "rcept_no": rcept_no,
    }

    response = requests.get(DART_DOCUMENT_URL, params=params, timeout=timeout)
    response.raise_for_status()

    return response.content


def extract_xml_from_zip(zip_content, rcept_no=None):
    zip_buffer = io.BytesIO(zip_content)

    if not zipfile.is_zipfile(zip_buffer):
        text = zip_content[:1000].decode("utf-8", errors="ignore")
        raise ValueError(
            "DART 응답이 ZIP이 아닙니다.\n"
            f"응답 내용:\n{text}"
        )

    zip_buffer.seek(0)

    with zipfile.ZipFile(zip_buffer) as zf:
        file_names = zf.namelist()
        logger.info("ZIP 내부 파일 목록: %s", file_names)

        xml_names = [
            name for name in file_names
            if name.lower().endswith(".xml")
        ]

        if not xml_names:
            raise ValueError("ZIP 내부에서 XML 파일을 찾을 수 없습니다.")

        if rcept_no:
            preferred = [
                name for name in xml_names
                if str(rcept_no) in name
            ]

            xml_name = preferred[0] if preferred else xml_names[0]
        else:
            xml_name = xml_names[0]

        logger.info("추출할 XML 파일: %s", xml_name)

        return zf.read(xml_name)


def decode_xml(xml_data):
    for encoding in ("euc-kr", "cp949", "utf-8"):
        try:
            return xml_data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return xml_data.decode("utf-8", errors="ignore")


def parse_html_from_xml(xml_data):
    xml_text = decode_xml(xml_data)
    return BeautifulSoup(xml_text, "html.parser")


def save_xml_file(xml_data, corp_name, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{safe_filename(corp_name)}.xml"
    file_path = output_dir / filename

    file_path.write_bytes(xml_data)

    logger.info("XML 저장 완료: %s", file_path)

    return file_path


def fetch_audit_report_by_corp_code(
    api_key,
    corp_code,
    output_dir="result",
    bgn_de=DEFAULT_BGN_DE,
    end_de=DEFAULT_END_DE,
):
    rcept_no, corp_name = get_latest_rcept_no(
        api_key=api_key,
        corp_code=corp_code,
        bgn_de=bgn_de,
        end_de=end_de,
    )

    zip_content = fetch_document_zip(api_key, rcept_no)
    xml_data = extract_xml_from_zip(zip_content, rcept_no)

    save_xml_file(
        xml_data=xml_data,
        corp_name=corp_name,
        output_dir=output_dir,
    )

    soup = parse_html_from_xml(xml_data)

    return soup


def download_documents_for_csv(
    api_key,
    input_csv,
    output_dir,
    corp_code_column="corp_code",
    bgn_de=DEFAULT_BGN_DE,
    end_de=DEFAULT_END_DE,
    env_path=None,
):
    if not api_key:
        api_key = resolve_api_key(env_path=env_path)

    corp_codes = load_corp_codes_from_csv(
        input_csv,
        corp_code_column=corp_code_column,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for corp_code in corp_codes:
        try:
            reports = fetch_opendart_list_records(
                api_key=api_key,
                corp_code=corp_code,
                bgn_de=bgn_de,
                end_de=end_de,
            )

            if not reports:
                logger.warning(
                    "기업 코드 %s에 대한 공시 목록을 찾을 수 없습니다.",
                    corp_code,
                )
                continue

            target_report = select_target_report(reports)

            rcept_no = target_report["rcept_no"]
            corp_name = target_report["corp_name"]

            logger.info("처리 중: %s / %s", corp_name, rcept_no)

            zip_content = fetch_document_zip(api_key, rcept_no)
            xml_data = extract_xml_from_zip(zip_content, rcept_no)

            file_path = save_xml_file(
                xml_data=xml_data,
                corp_name=corp_name,
                output_dir=output_dir,
            )

            saved_files.append(file_path)

        except Exception as error:
            logger.exception(
                "기업 코드 %s 처리 실패: %s",
                corp_code,
                error,
            )

    return saved_files


def parse_args():
    parser = argparse.ArgumentParser(
        description="DART Open API로 기업 공시 XML을 다운로드합니다."
    )

    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="DART API KEY",
    )

    parser.add_argument(
        "--input-csv",
        dest="input_csv",
        default=None,
        help="기업 코드 CSV 파일 경로",
    )

    parser.add_argument(
        "--corp-code",
        dest="corp_code",
        default=None,
        help="단일 기업 corp_code",
    )

    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="result",
        help="XML 저장 폴더",
    )

    parser.add_argument(
        "--corp-code-column",
        dest="corp_code_column",
        default="corp_code",
        help="CSV 내 기업 코드 컬럼명",
    )

    parser.add_argument(
        "--env-path",
        dest="env_path",
        default=None,
        help=".env 파일 경로",
    )

    parser.add_argument(
        "--bgn-de",
        dest="bgn_de",
        default=DEFAULT_BGN_DE,
        help="공시 검색 시작일 YYYYMMDD",
    )

    parser.add_argument(
        "--end-de",
        dest="end_de",
        default=DEFAULT_END_DE,
        help="공시 검색 종료일 YYYYMMDD",
    )

    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    args = parse_args()
    api_key = resolve_api_key(args=args, env_path=args.env_path)

    if args.input_csv:
        saved_files = download_documents_for_csv(
            api_key=api_key,
            input_csv=args.input_csv,
            output_dir=args.output_dir,
            corp_code_column=args.corp_code_column,
            bgn_de=args.bgn_de,
            end_de=args.end_de,
            env_path=args.env_path,
        )

        logger.info("저장된 파일 개수: %s", len(saved_files))

    elif args.corp_code:
        fetch_audit_report_by_corp_code(
            api_key=api_key,
            corp_code=args.corp_code,
            output_dir=args.output_dir,
            bgn_de=args.bgn_de,
            end_de=args.end_de,
        )

    else:
        raise ValueError(
            "--corp-code 또는 --input-csv 중 하나는 반드시 입력해야 합니다."
        )


if __name__ == "__main__":
    main()
