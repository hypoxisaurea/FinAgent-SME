import os
import requests
import pandas as pd
from pathlib import Path
from langchain_core.tools import tool
import opendartreader as OpenDartReader

ECOS_BASE = "https://ecos.bok.or.kr/api"
KOSIS_BASE = "https://kosis.kr/openapi/statisticsData.do"

# CSV 파일 경로
DATA_DIR = Path(__file__).parent / "data"
PROFIT_CSV  = DATA_DIR / "profit_ratio.csv"   # 손익 지표
ASSET_CSV   = DATA_DIR / "asset_ratio.csv"    # 자산/자본 지표


def _get_dart():
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise ValueError("환경변수 DART_API_KEY가 설정되지 않았습니다.")
    return OpenDartReader.OpenDartReader(api_key)


def _ecos_get(stat_code: str, item_code: str, period: str) -> list[dict]:
    api_key = os.environ.get("ECOS_API_KEY")
    if not api_key:
        raise ValueError("환경변수 ECOS_API_KEY가 설정되지 않았습니다.")
    url = (
        f"{ECOS_BASE}/StatisticSearch/{api_key}/json/kr/1/100"
        f"/{stat_code}/A/{period}/{period}/{item_code}"
    )
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    return res.json().get("StatisticSearch", {}).get("row", [])


def _kosis_get(org_id: str, tbl_id: str, item_id: str, period: str) -> list[dict]:
    api_key = os.environ.get("KOSIS_API_KEY")
    if not api_key:
        raise ValueError("환경변수 KOSIS_API_KEY가 설정되지 않았습니다.")
    params = {
        "method": "getList", "apiKey": api_key, "format": "json",
        "jsonVD": "Y", "orgId": org_id, "tblId": tbl_id,
        "itmId": item_id, "prdSe": "Y",
        "startPrdDe": period, "endPrdDe": period,
    }
    res = requests.get(KOSIS_BASE, params=params, timeout=10)
    res.raise_for_status()
    return res.json()


# DART induty_code 앞 2자리 → KSIC 대분류 (CSV 업종코드 기준)
# CSV에 없는 업종: K(금융), O(공공행정), Q(보건), S94(협회), T, U
_INDUTY_TO_KSIC = {
    # A. 농업, 임업 및 어업
    "01": "A01 농업",
    "02": None,           # 임업 - CSV 없음
    "03": "A03 어업",
    # B. 광업
    "05": "B 광업",
    "06": "B 광업",
    "07": "B 광업",
    "08": "B 광업",
    # C. 제조업
    "10": "C 제조업", "11": "C 제조업", "12": "C 제조업",
    "13": "C 제조업", "14": "C 제조업", "15": "C 제조업",
    "16": "C 제조업", "17": "C 제조업", "18": "C 제조업",
    "19": "C 제조업", "20": "C 제조업", "21": "C 제조업",
    "22": "C 제조업", "23": "C 제조업", "24": "C 제조업",
    "25": "C 제조업", "26": "C 제조업", "27": "C 제조업",
    "28": "C 제조업", "29": "C 제조업", "30": "C 제조업",
    "31": "C 제조업", "32": "C 제조업", "33": "C 제조업",
    "34": "C 제조업",
    # D. 전기, 가스, 증기 및 공기조절 공급업
    "35": "D35 전기, 가스, 증기 및 공기조절 공급업",
    # E. 수도, 하수 및 폐기물 처리, 원료 재생업
    "36": None,           # 수도업 - CSV 없음
    "37": "E37-39 하수 · 폐기물 처리, 원료재생업",
    "38": "E37-39 하수 · 폐기물 처리, 원료재생업",
    "39": "E37-39 하수 · 폐기물 처리, 원료재생업",
    # F. 건설업
    "41": "F 건설업",
    "42": "F 건설업",
    # G. 도매 및 소매업
    "45": "G 도매 및 소매업",
    "46": "G 도매 및 소매업",
    "47": "G 도매 및 소매업",
    # H. 운수 및 창고업
    "49": "H 운수 및 창고업",
    "50": "H 운수 및 창고업",
    "51": "H 운수 및 창고업",
    "52": "H 운수 및 창고업",
    # I. 숙박 및 음식점업
    "55": "I 숙박 및 음식점업",
    "56": "I 숙박 및 음식점업",
    # J. 정보통신업
    "58": "J 정보통신업",
    "59": "J 정보통신업",
    "60": "J 정보통신업",
    "61": "J 정보통신업",
    "62": "J 정보통신업",
    "63": "J 정보통신업",
    # K. 금융 및 보험업 - CSV 없음
    "64": None,
    "65": None,
    "66": None,
    # L. 부동산업
    "68": "L 부동산업",
    # M. 전문, 과학 및 기술 서비스업
    "70": None,           # 연구개발업 - CSV 없음
    "71": "M 전문, 과학 및 기술 서비스업",
    "72": "M 전문, 과학 및 기술 서비스업",
    "73": "M 전문, 과학 및 기술 서비스업",
    # N. 사업시설 관리, 사업 지원 및 임대 서비스업
    "74": "N 사업시설 관리 및 사업지원 및 임대 서비스업",
    "75": "N 사업시설 관리 및 사업지원 및 임대 서비스업",
    "76": "N 사업시설 관리 및 사업지원 및 임대 서비스업",
    # O. 공공 행정 - CSV 없음
    "84": None,
    # P. 교육 서비스업
    "85": "P 교육 서비스업",
    # Q. 보건업 및 사회복지 서비스업 - CSV 없음
    "86": None,
    "87": None,
    # R. 예술, 스포츠 및 여가관련 서비스업
    "90": "R 예술, 스포츠 및 여가관련 서비스업",
    "91": "R 예술, 스포츠 및 여가관련 서비스업",
    # S. 협회 및 단체, 수리 및 기타 개인 서비스업
    "94": None,           # 협회 및 단체 - CSV 없음
    "95": "S95 개인 및 소비용품 수리업",
    "96": "S96 기타 개인 서비스업",
    # T. 가구 내 고용활동 - CSV 없음
    "97": None,
    "98": None,
    # U. 국제 및 외국기관 - CSV 없음
    "99": None,
}


@tool
def map_corp_to_ksic(corp_code: str) -> str:
    """DART 회사개황의 업종코드를 KSIC 코드로 변환."""
    dart = _get_dart()
    info = dart.company(corp_code)
    if info is None:
        raise ValueError(f"corp_code={corp_code} 회사 정보 없음")
    induty = str(info.get("induty_code", ""))
    induty_2digit = induty[:2]
    ksic = _INDUTY_TO_KSIC.get(induty_2digit)
    if ksic is None:
        return f"N/A (업종코드 {induty} - 산업평균 데이터 없음)"
    return ksic


@tool
def get_industry_avg_ratios(ksic_code: str, year: int) -> dict:
    """한국은행 기업경영분석 CSV에서 KSIC 업종 중소기업 평균 재무비율 조회.

    손익 지표: 매출액영업이익률
    자산/자본 지표: 부채비율, 유동비율
    """
    if ksic_code.startswith("N/A"):
        return {
            "avg_op_margin": None, "avg_debt_ratio": None,
            "avg_current_ratio": None, "ksic_code": ksic_code,
            "year": year, "note": "산업평균 데이터 없음"
        }

    year_str = str(year)

    def _read(csv_path, account_nm, ksic):
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        df_filtered = df[
            (df["업종코드"].str.strip() == ksic) &
            (df["계정항목"].str.strip() == account_nm) &
            (df["기업규모"].str.strip() == "중소기업")
        ]
        if df_filtered.empty or year_str not in df_filtered.columns:
            return None
        val = df_filtered.iloc[0][year_str]
        return float(val) if pd.notna(val) else None

    op_margin   = _read(PROFIT_CSV,  "매출액영업이익률", ksic_code)
    debt_ratio  = _read(ASSET_CSV,   "부채비율",        ksic_code)
    curr_ratio  = _read(ASSET_CSV,   "유동비율",        ksic_code)

    return {
        "avg_op_margin":     op_margin / 100 if op_margin is not None else None,
        "avg_debt_ratio":    debt_ratio / 100 if debt_ratio is not None else None,
        "avg_current_ratio": curr_ratio / 100 if curr_ratio is not None else None,
        "ksic_code": ksic_code,
        "year": year,
    }


@tool
def compare_to_industry(company_ratios: dict, industry_avg: dict) -> dict:
    """기업 비율 vs 산업평균 비교. 편차 ±10% 이상이면 above/below."""
    def _pos(company_val, avg_val):
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
    """KOSIS 광공업생산지수에서 산업생산·재고·출하지수 조회 후 업황 등급 산출."""
    api_key = os.environ.get("KOSIS_API_KEY")
    url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    params = {
        "method":       "getList",
        "apiKey":       api_key,
        "itmId": "T10 T11 T12",
        "objL1":        "ALL",
        "format":       "json",
        "jsonVD":       "Y",
        "prdSe":        "M",
        "newEstPrdCnt": "13",
        "orgId":        "101",
        "tblId":        "DT_1F02011",
    }
    res = requests.get(url, params=params, timeout=10)
    data = res.json()

    if not isinstance(data, list):
        return {"production_index_yoy": 0, "inventory_index_yoy": 0,
                "shipment_index_yoy": 0, "outlook_score": "Medium"}

    production_vals, inventory_vals, shipment_vals = [], [], []
    for row in data:
        itm = row.get("ITM_ID", "")
        val = float(row.get("DT", 0) or 0)
        if itm == "T10":   production_vals.append(val)
        elif itm == "T11": inventory_vals.append(val)
        elif itm == "T12": shipment_vals.append(val)

    def _yoy(vals):
        if len(vals) >= 13:
            return (vals[-1] - vals[-13]) / vals[-13]
        return 0.0

    production_yoy = _yoy(production_vals)
    inventory_yoy  = _yoy(inventory_vals)
    shipment_yoy   = _yoy(shipment_vals)

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
        "outlook_score":        score,
    }


@tool
def get_macro_indicators() -> dict:
    """한국은행 ECOS에서 기준금리·원달러환율 최근치 조회."""
    api_key = os.environ.get("ECOS_API_KEY")

    # 기준금리 (연간)
    rate_rows = _ecos_get("722Y001", "0101000", "2024")
    base_rate = float(rate_rows[-1]["DATA_VALUE"]) if rate_rows else None
    trend = "stable"
    if len(rate_rows) >= 2:
        diff = float(rate_rows[-1]["DATA_VALUE"]) - float(rate_rows[-2]["DATA_VALUE"])
        trend = "rising" if diff > 0 else ("falling" if diff < 0 else "stable")

    # 원달러 환율 (일별, 최근 5일)
    url = (
        f"{ECOS_BASE}/StatisticSearch/{api_key}/json/kr/1/5"
        f"/731Y001/D/20240101/20241231/0000001"
    )
    res = requests.get(url, timeout=10)
    fx_rows = res.json().get("StatisticSearch", {}).get("row", [])
    usd_krw = float(fx_rows[-1]["DATA_VALUE"]) if fx_rows else None

    return {"base_rate": base_rate, "usd_krw": usd_krw, "rate_trend": trend}
