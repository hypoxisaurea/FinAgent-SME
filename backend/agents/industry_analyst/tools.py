import os
import requests
from langchain_core.tools import tool
import OpenDartReader

ECOS_BASE = "https://ecos.bok.or.kr/api"
KOSIS_BASE = "https://kosis.kr/openapi/statisticsData.do"


def _get_dart():
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise ValueError("환경변수 DART_API_KEY가 설정되지 않았습니다.")
    return OpenDartReader(api_key)


def _ecos_get(stat_code: str, item_code: str, period: str) -> list[dict]:
    """ECOS Open API 공통 호출 함수."""
    api_key = os.environ.get("ECOS_API_KEY")
    if not api_key:
        raise ValueError("환경변수 ECOS_API_KEY가 설정되지 않았습니다.")
    url = (
        f"{ECOS_BASE}/StatisticSearch/{api_key}/json/kr/1/100"
        f"/{stat_code}/A/{period}/{period}/{item_code}"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    data = res.json()
    return data.get("StatisticSearch", {}).get("row", [])


def _kosis_get(org_id: str, tbl_id: str, item_id: str, period: str) -> list[dict]:
    """KOSIS Open API 공통 호출 함수."""
    api_key = os.environ.get("KOSIS_API_KEY")
    if not api_key:
        raise ValueError("환경변수 KOSIS_API_KEY가 설정되지 않았습니다.")
    params = {
        "method":    "getList",
        "apiKey":    api_key,
        "format":    "json",
        "jsonVD":    "Y",
        "orgId":     org_id,
        "tblId":     tbl_id,
        "itmId":     item_id,
        "prdSe":     "Y",
        "startPrdDe": period,
        "endPrdDe":   period,
    }
    res = requests.get(KOSIS_BASE, params=params, timeout=10)
    res.raise_for_status()
    return res.json()


# DART induty_code → KSIC 대분류 매핑 테이블 (주요 업종 중심)
_INDUTY_TO_KSIC = {
    "제조업":           "C",
    "건설업":           "F",
    "도매및소매업":     "G",
    "운수및창고업":     "H",
    "정보통신업":       "J",
    "금융및보험업":     "K",
    "부동산업":         "L",
    "전문과학기술":     "M",
    "음식숙박업":       "I",
}


@tool
def map_corp_to_ksic(corp_code: str) -> str:
    """DART 회사개황의 업종(induty_code)을 KSIC 코드로 변환."""
    dart = _get_dart()
    info = dart.company(corp_code)
    if info is None or info.empty:
        raise ValueError(f"corp_code={corp_code} 회사 정보 없음")

    induty = str(info.iloc[0].get("induty_code", ""))
    # DART induty_code가 KSIC와 1:1이 아니므로 부분 문자열 매칭
    for keyword, ksic in _INDUTY_TO_KSIC.items():
        if keyword in induty:
            return ksic
    return "C"  # 매핑 실패 시 제조업(C)으로 기본값


@tool
def get_industry_avg_ratios(ksic_code: str, year: int) -> dict:
    """한국은행 ECOS '기업경영분석' 통계에서 KSIC 산업평균 재무비율 조회.

    통계표코드 015Y003: 산업별 경영분석 (부채비율, 영업이익률 등)
    """
    period = str(year)
    rows = _ecos_get(stat_code="015Y003", item_code=ksic_code, period=period)

    result = {
        "avg_debt_ratio":    None,
        "avg_op_margin":     None,
        "avg_current_ratio": None,
        "ksic_code": ksic_code,
        "year": year,
    }
    for row in rows:
        nm = row.get("ITEM_NAME", "")
        val = float(row.get("DATA_VALUE", 0) or 0)
        if "부채비율" in nm:
            result["avg_debt_ratio"] = val / 100
        elif "영업이익률" in nm:
            result["avg_op_margin"] = val / 100
        elif "유동비율" in nm:
            result["avg_current_ratio"] = val / 100

    return result


@tool
def compare_to_industry(company_ratios: dict, industry_avg: dict) -> dict:
    """기업 비율 vs 산업평균 비교.

    편차 ±10% 이상이면 above/below, 이내면 in-line으로 분류.
    """
    def _pos(company_val: float, avg_val: float | None) -> str:
        if avg_val is None or avg_val == 0:
            return "n/a"
        if company_val > avg_val * 1.1:
            return "above"
        if company_val < avg_val * 0.9:
            return "below"
        return "in-line"

    return {
        "debt_ratio":    _pos(company_ratios.get("debt_ratio", 0),    industry_avg.get("avg_debt_ratio")),
        "op_margin":     _pos(company_ratios.get("op_margin", 0),     industry_avg.get("avg_op_margin")),
        "current_ratio": _pos(company_ratios.get("current_ratio", 0), industry_avg.get("avg_current_ratio")),
    }


@tool
def get_industry_outlook(ksic_code: str) -> dict:
    """KOSIS 광공업생산지수(통계청)에서 산업생산·재고·출하지수 조회 후 업황 등급 산출.

    등급 기준
    - High  : 생산지수 YoY -10% 이하 + 재고 증가
    - Medium: 생산지수 YoY -5% ~ -10% 또는 재고 소폭 증가
    - Low   : 생산지수 YoY 0% 이상
    """
    # KOSIS 광공업생산지수: orgId=101, tblId=DT_1F002
    rows = _kosis_get(org_id="101", tbl_id="DT_1F002",
                      item_id=ksic_code, period="2024")

    production_yoy = 0.0
    inventory_yoy  = 0.0
    shipment_yoy   = 0.0

    for row in rows:
        nm  = row.get("ITM_NM", "")
        val = float(row.get("DT", 0) or 0)
        if "생산" in nm:
            production_yoy = (val - 100) / 100
        elif "재고" in nm:
            inventory_yoy  = (val - 100) / 100
        elif "출하" in nm:
            shipment_yoy   = (val - 100) / 100

    if production_yoy <= -0.10 and inventory_yoy > 0:
        score = "High"
    elif production_yoy <= -0.05 or inventory_yoy > 0.05:
        score = "Medium"
    else:
        score = "Low"

    return {
        "production_index_yoy": round(production_yoy, 4),
        "inventory_index_yoy":  round(inventory_yoy, 4),
        "shipment_index_yoy":   round(shipment_yoy, 4),
        "outlook_score": score,
    }


@tool
def get_macro_indicators() -> dict:
    """한국은행 ECOS에서 기준금리·원달러환율 최근치 조회.

    통계표코드
    - 722Y001: 기준금리
    - 731Y003: 원달러 환율(매매기준율)
    """
    rate_rows = _ecos_get("722Y001", "0101000", "2024")
    fx_rows   = _ecos_get("731Y003", "0000001", "2024")

    base_rate = float(rate_rows[-1]["DATA_VALUE"]) if rate_rows else None
    usd_krw   = float(fx_rows[-1]["DATA_VALUE"])   if fx_rows   else None

    # 금리 추세: 직전 값 대비 판단
    trend = "stable"
    if len(rate_rows) >= 2:
        diff = float(rate_rows[-1]["DATA_VALUE"]) - float(rate_rows[-2]["DATA_VALUE"])
        if diff > 0:
            trend = "rising"
        elif diff < 0:
            trend = "falling"

    return {
        "base_rate":  base_rate,
        "usd_krw":    usd_krw,
        "rate_trend": trend,
    }
    
