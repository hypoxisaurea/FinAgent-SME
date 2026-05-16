import os
from langchain_core.tools import tool


@tool
def map_corp_to_ksic(corp_code: str) -> str:
    """DART 회사개황의 induty_code를 KSIC 5자리로 변환."""
    # TODO: dart.company(corp_code)["induty_code"] → KSIC 매핑 테이블 적용
    return "C26110"  # 예시: 반도체 제조업


@tool
def get_industry_avg_ratios(ksic_code: str, year: int) -> dict:
    """한국은행 ECOS 기업경영분석에서 KSIC 산업평균 재무비율 조회."""
    # TODO: ECOS Open API 호출 (ecos.bok.or.kr/api)
    return {
        "avg_debt_ratio":    0.80,
        "avg_op_margin":     0.075,
        "avg_current_ratio": 1.45,
        "sample_size": 312,
        "ksic_code": ksic_code,
        "year": year,
    }


@tool
def compare_to_industry(company_ratios: dict, industry_avg: dict) -> dict:
    """기업 비율 vs 산업평균 비교 결과를 dict로 반환.

    편차가 ±10% 이상이면 above/below, 이내면 in-line으로 분류한다.
    """
    def _pos(company_val: float, avg_val: float) -> str:
        if company_val > avg_val * 1.1:
            return "above"
        if company_val < avg_val * 0.9:
            return "below"
        return "in-line"

    return {
        "debt_ratio":    _pos(company_ratios["debt_ratio"],    industry_avg["avg_debt_ratio"]),
        "op_margin":     _pos(company_ratios["op_margin"],     industry_avg["avg_op_margin"]),
        "current_ratio": _pos(company_ratios["current_ratio"], industry_avg["avg_current_ratio"]),
    }


@tool
def get_industry_outlook(ksic_code: str) -> dict:
    """KOSIS에서 최근 12개월 산업생산·재고·출하지수 추세 조회 후 룰베이스 등급 산출.

    등급 기준 (예시)
    - High  : 생산지수 YoY -10% 이하 + 재고 증가
    - Medium: 생산지수 YoY -5% ~ -10% 또는 재고 소폭 증가
    - Low   : 생산지수 YoY 0% 이상
    """
    # TODO: KOSIS Open API 호출
    return {
        "production_index_yoy": -0.04,
        "inventory_index_yoy":   0.12,
        "shipment_index_yoy":   -0.06,
        "outlook_score": "Medium",   # Low / Medium / High
    }


@tool
def get_macro_indicators() -> dict:
    """한국은행 ECOS에서 기준금리·원달러환율 최근치 조회."""
    # TODO: ECOS Open API 호출
    return {
        "base_rate":   3.25,
        "usd_krw":     1370,
        "rate_trend":  "stable",
    }
