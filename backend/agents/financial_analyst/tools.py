import os
import pandas as pd
from langchain_core.tools import tool
import opendartreader as OpenDartReader


def _get_dart():
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        raise ValueError("환경변수 DART_API_KEY가 설정되지 않았습니다.")
    dart = OpenDartReader.OpenDartReader(api_key)
    return dart


def _normalize_accounts(fs: pd.DataFrame) -> dict:
    """DART finstate_all 결과에서 필요한 계정과목만 추출."""

    def _get(account_nm: str, sj_div: str = None) -> float:
        df = fs
        if sj_div:
            df = fs[fs["sj_div"] == sj_div]
        row = df[df["account_nm"].str.strip() == account_nm]
        if row.empty:
            return None
        val = row.iloc[0]["thstrm_amount"]
        if pd.isna(val) or val == "":
            return None
        return float(str(val).replace(",", ""))

    is_div = "IS" if not fs[fs["sj_div"] == "IS"].empty else "CIS"

    return {
        "유동자산": _get("유동자산",   "BS"),
        "유동부채": _get("유동부채",   "BS"),
        "총자산": _get("자산총계",   "BS"),
        "자본총계": _get("자본총계",   "BS"),
        "부채총계": _get("부채총계",   "BS"),
        "이익잉여금": _get("이익잉여금", "BS") or _get("이익잉여금(결손금)", "BS"),
        "매출액": _get("영업수익", is_div) or _get("수익(매출액)", is_div) or _get("매출액", is_div),
        "영업이익": _get("영업이익",   is_div) or _get("영업이익(손실)", is_div),
        "당기순이익": _get("당기순이익(손실)", is_div) or _get("당기순이익", is_div),
        "이자비용": _get("금융비용",   is_div),
        "영업현금흐름": _get("영업활동현금흐름", "CF") or _get("영업활동 현금흐름", "CF"),
    }
    return {k: v if v is not None else 0.0 for k, v in result.items()}
    raise ValueError("재무제표 데이터를 파싱할 수 없습니다.")


@tool
def get_financial_statements(corp_code: str, year: int) -> dict:
    """DART에서 corp_code 기업의 year 연도 재무제표를 가져와
    표준 계정과목 dict로 반환한다."""
    dart = _get_dart()
    fs = dart.finstate_all(corp_code, year)
    if fs is None or fs.empty:
        raise ValueError(f"corp_code={corp_code}, year={year} 재무제표 없음")
    return _normalize_accounts(fs)


@tool
def calc_financial_ratios(fs: dict) -> dict:
    """재무제표 dict에서 6종 재무비율과 현금흐름 비율을 계산한다."""
    return {
        "debt_ratio":        fs["부채총계"] / max(fs["자본총계"], 1),
        "current_ratio":     fs["유동자산"] / max(fs["유동부채"], 1),
        "roa":               fs["당기순이익"] / max(fs["총자산"], 1),
        "op_margin":         fs["영업이익"] / max(fs["매출액"], 1),
        "interest_coverage": fs["영업이익"] / max(fs["이자비용"], 1),
        "ocf_to_sales":      fs["영업현금흐름"] / max(fs["매출액"], 1),
        "ocf_to_net_income": fs["영업현금흐름"] / fs["당기순이익"] if fs["당기순이익"] != 0 else None,
    }


@tool
def calc_altman_z_prime(fs: dict) -> dict:
    """비상장 중소기업용 Altman Z'-Score (1983) 계산.

    Z' = 0.717·X1 + 0.847·X2 + 3.107·X3 + 0.420·X4 + 0.998·X5
      X1 = 운전자본 / 총자산
      X2 = 이익잉여금 / 총자산
      X3 = 영업이익 / 총자산
      X4 = 자본총계(장부가) / 부채총계
      X5 = 매출액 / 총자산

    판정: Z' > 2.9 Safe / 1.23 <= Z' <= 2.9 Grey / Z' < 1.23 Distress
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
        "components": {"X1": round(x1,4), "X2": round(x2,4),
                       "X3": round(x3,4), "X4": round(x4,4), "X5": round(x5,4)},
    }


@tool
def trend_analysis(corp_code: str, years: list[int]) -> dict:
    """최근 3개년 재무비율의 급변 항목을 플래그로 반환.

    부채비율 YoY +20%p 이상 급증, 영업이익률 YoY -5%p 이상 급락을 위험 신호로 감지.
    """
    dart = _get_dart()
    history = []

    for year in sorted(years):
        fs_raw = dart.finstate_all(corp_code, year)
        if fs_raw is None or fs_raw.empty:
            continue
        fs = _normalize_accounts(fs_raw)
        debt_ratio = fs["부채총계"] / max(fs["자본총계"], 1)
        op_margin  = fs["영업이익"] / max(fs["매출액"], 1) if fs["매출액"] > 0 else 0
        history.append({
            "year":       year,
            "debt_ratio": debt_ratio,
            "op_margin":  round(op_margin, 4),
            "ocf":        fs["영업현금흐름"],
        })

    flags = []
    yoy = {"debt_ratio": [], "op_margin": []}

    for i in range(1, len(history)):
        prev, curr = history[i - 1], history[i]
        debt_chg   = curr["debt_ratio"] - prev["debt_ratio"]
        margin_chg = curr["op_margin"]  - prev["op_margin"]

        yoy["debt_ratio"].append(round(debt_chg, 4))
        yoy["op_margin"].append(round(margin_chg, 4))

        if debt_chg >= 0.2:
            flags.append(f"{curr['year']}_debt_ratio_spike_+{debt_chg:.0%}")
        if margin_chg <= -0.05:
            flags.append(f"{curr['year']}_op_margin_drop_{margin_chg:.0%}")
        if curr["ocf"] < 0:
            flags.append(f"{curr['year']}_negative_operating_cashflow")

    return {"flags": flags, "yoy": yoy, "history": history}
