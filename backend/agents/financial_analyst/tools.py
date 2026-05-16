import os
from langchain_core.tools import tool


@tool
def get_financial_statements(corp_code: str, year: int) -> dict:
    """DART에서 corp_code 기업의 year 연도 재무제표를 가져와
    표준 계정과목 dict로 반환한다."""
    # TODO: OpenDartReader 연동
    # import OpenDartReader
    # dart = OpenDartReader(os.environ["DART_API_KEY"])
    # fs = dart.finstate_all(corp_code, year)
    # return _normalize_accounts(fs)
    return {
        "유동자산":      1_000_000,
        "유동부채":        600_000,
        "총자산":        3_000_000,
        "자본총계":      1_200_000,
        "부채총계":      1_800_000,
        "이익잉여금":      500_000,
        "매출액":        2_500_000,
        "영업이익":        180_000,
        "당기순이익":      120_000,
        "이자비용":         40_000,
        "영업현금흐름":    150_000,
    }


@tool
def calc_financial_ratios(fs: dict) -> dict:
    """재무제표 dict에서 5종 재무비율과 현금흐름 비율을 계산한다."""
    return {
        "debt_ratio":        fs["부채총계"] / max(fs["자본총계"], 1),
        "current_ratio":     fs["유동자산"] / max(fs["유동부채"], 1),
        "roa":               fs["당기순이익"] / max(fs["총자산"], 1),
        "op_margin":         fs["영업이익"] / max(fs["매출액"], 1),
        "interest_coverage": fs["영업이익"] / max(fs["이자비용"], 1),
        "ocf_to_sales":      fs["영업현금흐름"] / max(fs["매출액"], 1),
    }


@tool
def calc_altman_z_prime(fs: dict) -> dict:
    """비상장 중소기업용 Altman Z'-Score (1983) 계산.

    Z' = 0.717·X1 + 0.847·X2 + 3.107·X3 + 0.420·X4 + 0.998·X5
      X1 = 운전자본 / 총자산
      X2 = 이익잉여금 / 총자산
      X3 = 영업이익 / 총자산
      X4 = 자본총계(장부가) / 부채총계   ← 비상장용
      X5 = 매출액 / 총자산

    판정: Z' > 2.9 Safe / 1.23 ≤ Z' ≤ 2.9 Grey / Z' < 1.23 Distress
    """
    ta = max(fs["총자산"], 1)
    x1 = (fs["유동자산"] - fs["유동부채"]) / ta
    x2 = fs["이익잉여금"] / ta
    x3 = fs["영업이익"] / ta
    x4 = fs["자본총계"] / max(fs["부채총계"], 1)
    x5 = fs["매출액"] / ta

    z = 0.717*x1 + 0.847*x2 + 3.107*x3 + 0.420*x4 + 0.998*x5

    if z > 2.9:
        zone = "Safe"
    elif z >= 1.23:
        zone = "Grey"
    else:
        zone = "Distress"

    return {
        "z_prime": round(z, 3),
        "zone": zone,
        "components": {"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5},
    }


@tool
def trend_analysis(corp_code: str, years: list[int]) -> dict:
    """최근 3개년 재무비율의 급변 항목을 플래그로 반환.

    부채비율 급증, 영업이익률 급락 등 이상 패턴을 감지한다.
    """
    # TODO: years 만큼 get_financial_statements 호출 후 YoY 비교
    return {
        "flags": ["debt_ratio_spike_YoY+35%"],
        "yoy": {"debt_ratio": [0.95, 1.10, 1.50]},
    }
