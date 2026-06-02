from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

ECOS_API_KEY_ENV = "ECOS_API_KEY"
ECOS_BASE_URL = "https://ecos.bok.or.kr/api"
KOSIS_API_KEY_ENV = "KOSIS_API_KEY"
KOSIS_PARAM_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"


def get_ecos_api_key(*, required: bool = True) -> str | None:
    """환경에서 ECOS API 키를 읽어 반환한다."""
    api_key = os.getenv(ECOS_API_KEY_ENV, "").strip()
    if api_key:
        return api_key
    if required:
        raise ValueError(f"환경변수 {ECOS_API_KEY_ENV}가 설정되지 않았습니다.")
    return None


def fetch_ecos_statistic_rows(
    stat_code: str,
    cycle: str,
    start_period: str,
    end_period: str,
    item_code: str,
    *,
    start_row: int = 1,
    end_row: int = 100,
    lang: str = "kr",
    format_name: str = "json",
    timeout: int = 10,
) -> list[dict[str, Any]]:
    """ECOS 통계 조회 응답의 row 목록을 반환한다."""
    api_key = get_ecos_api_key()
    url = (
        f"{ECOS_BASE_URL}/StatisticSearch/{api_key}/{format_name}/{lang}/"
        f"{start_row}/{end_row}/{stat_code}/{cycle}/{start_period}/"
        f"{end_period}/{item_code}"
    )
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    payload = response.json()
    rows = payload.get("StatisticSearch", {}).get("row", [])
    return rows if isinstance(rows, list) else []


def extract_ecos_float_series(
    rows: list[dict[str, Any]],
    *,
    value_key: str = "DATA_VALUE",
) -> list[float]:
    """ECOS row 목록에서 숫자 시계열만 추출한다."""
    values: list[float] = []
    for row in rows:
        raw_value = row.get(value_key)
        if raw_value in (None, ""):
            continue
        try:
            values.append(float(raw_value))
        except (TypeError, ValueError):
            continue
    return values


def get_kosis_api_key(*, required: bool = False) -> str | None:
    """환경에서 KOSIS API 키를 읽어 반환한다."""
    api_key = os.getenv(KOSIS_API_KEY_ENV, "").strip()
    if api_key:
        return api_key
    if required:
        raise ValueError(f"환경변수 {KOSIS_API_KEY_ENV}가 설정되지 않았습니다.")
    return None


def fetch_kosis_parameter_data(
    tbl_id: str,
    *,
    itm_id: str = "ALL",
    obj_l1: str = "ALL",
    count: int = 13,
    org_id: str = "101",
    prd_se: str = "M",
    timeout: int = 10,
) -> list[dict[str, Any]]:
    """KOSIS Param API 공통 조회."""
    api_key = get_kosis_api_key(required=False)
    if not api_key:
        return []

    params = {
        "method": "getList",
        "apiKey": api_key,
        "itmId": itm_id,
        "objL1": obj_l1,
        "format": "json",
        "jsonVD": "Y",
        "prdSe": prd_se,
        "newEstPrdCnt": str(count),
        "orgId": org_id,
        "tblId": tbl_id,
    }
    try:
        response = requests.get(KOSIS_PARAM_URL, params=params, timeout=timeout)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("kosis_api_request_failed tbl_id=%s error=%s", tbl_id, exc)
        return []

    return data if isinstance(data, list) else []


def extract_kosis_yoy_from_rows(
    rows: list[dict[str, Any]],
    name_keyword: str,
    *,
    itm_keyword: str = "불변",
) -> float | None:
    """KOSIS row 목록에서 업종/항목 조건에 맞는 최근 YoY를 계산한다."""
    values: list[tuple[str, float]] = []
    for row in rows:
        c1_nm = str(row.get("C1_NM") or row.get("C1_OBJ_NM") or "")
        itm_nm = str(row.get("ITM_NM") or row.get("ITM_ID") or "")
        period = str(row.get("PRD_DE") or "")

        if name_keyword not in c1_nm:
            continue
        if itm_keyword and itm_keyword not in itm_nm:
            continue

        try:
            numeric_value = float(row.get("DT") or 0)
        except (TypeError, ValueError):
            continue

        if numeric_value > 0 and period:
            values.append((period, numeric_value))

    values.sort(key=lambda value: value[0])
    if len(values) < 13:
        return None

    previous = values[-13][1]
    current = values[-1][1]
    return (current - previous) / previous if previous != 0 else None

