import logging

import pandas as pd
from backend.backend_env import load_backend_env
from backend.integrations import dart_client
from langchain_core.tools import tool

load_backend_env()

logger = logging.getLogger(__name__)
OpenDartReader = dart_client.OpenDartReader


def _get_dart():
    return dart_client.get_dart_client()


def _fetch_audit_opinion(corp_code: str, year: int) -> tuple[str | None, bool]:
    """DART 회계감사인의 명칭 및 감사의견 API로 감사의견과 외감 여부를 반환한다."""
    api_key = dart_client.get_dart_api_key(required=False)
    if not api_key:
        logger.warning("OPEN_DART_API_KEY 미설정 - 감사의견 조회 생략")
        return None, False

    params = {
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": "11011",
    }

    try:
        data = dart_client.get_dart_json(
            "accnutAdtorNmNdAdtOpinion.json",
            params=params,
            timeout=5,
        )
    except ConnectionError as exc:
        logger.warning(
            "감사의견 API 호출 실패 corp_code=%s year=%s: %s",
            corp_code,
            year,
            exc,
        )
        return None, False

    if data.get("status") != "000":
        logger.info(
            "감사의견 데이터 없음 corp_code=%s year=%s status=%s",
            corp_code, year, data.get("status"),
        )
        return None, False

    items: list[dict] = data.get("list", [])
    if not items:
        return None, False

    target = next(
        (item for item in items if "당기" in item.get("bsns_year", "")),
        items[0],
    )

    opinion_text = target.get("adt_opinion", "").strip()
    opinion: str | None = opinion_text if opinion_text not in ("", "-") else None

    return opinion, True


def _normalize_accounts(fs: pd.DataFrame) -> dict:
    """DART finstate_all 결과에서 필요한 계정과목만 추출."""

    def _get(
        account_nm: str,
        sj_div: str | None = None,
        account_id: str | None = None,
    ) -> float | None:
        df = fs
        if sj_div:
            df = fs[fs["sj_div"] == sj_div]

        # 1. 표준 계정코드(account_id)가 들어오면 최우선으로 정확히 저격
        if account_id:
            row = df[df["account_id"].str.strip() == account_id]
        else:
            row = pd.DataFrame()

        # 2. 코드로 못 찾았거나 없을 경우, 모든 종류의 공백(\xa0 포함)을 제거하고 텍스트 매칭
        if row.empty:
            clean_nm = account_nm.replace(" ", "")
            row = df[df["account_nm"].str.replace(r"\s+", "", regex=True) == clean_nm]

        if row.empty:
            return None
        val = row.iloc[0]["thstrm_amount"]
        if pd.isna(val) or val == "":
            return None
        return float(str(val).replace(",", ""))

    is_div = "IS" if not fs[fs["sj_div"] == "IS"].empty else "CIS"

    result = {
        # ── 재무상태표 ──────────────────────────────────────────
        "유동자산":   _get("유동자산",   "BS"),
        "유동부채":   _get("유동부채",   "BS"),
        "총자산":     _get("자산총계",   "BS"),
        "자본총계":   _get("자본총계",   "BS"),
        "부채총계":   _get("부채총계",   "BS"),
        "이익잉여금": _get("이익잉여금", "BS") or _get("이익잉여금(결손금)", "BS"),

        # 활동성 지표용
        "재고자산":   _get("재고자산",   "BS"),
        "매출채권":   (
            _get("매출채권", "BS")
            or _get("매출채권 및 기타채권", "BS")
            or _get("매출채권및기타채권", "BS")
        ),
        "매입채무":   (
            _get("매입채무", "BS")
            or _get("매입채무 및 기타채무", "BS")
            or _get("매입채무및기타채무", "BS")
        ),

        # 차입금 구성
        "단기차입금": (
            _get("단기차입금", "BS")
            or _get("단기차입부채", "BS")
        ),
        "유동성장기차입금": (
            _get("유동성장기차입금", "BS")
            or _get("유동성성장기차입부채", "BS")
        ),
        "장기차입금": (
            _get("장기차입금", "BS")
            or _get("장기차입부채", "BS")
        ),
        "사채":       _get("사채", "BS"),

        # 유형자산
        "유형자산":   _get("유형자산",   "BS"),

        # ── 손익계산서 ──────────────────────────────────────────
        "매출액": (
            _get("영업수익",     is_div)
            or _get("수익(매출액)", is_div)
            or _get("매출액",     is_div)
        ),
        "매출원가": (
            _get("매출원가",     is_div)
            or _get("영업비용",  is_div)
        ),
        "영업이익":   _get("영업이익",          is_div) or _get("영업이익(손실)",   is_div),
        "당기순이익": _get("당기순이익(손실)",   is_div) or _get("당기순이익",       is_div),
        "이자비용":   _get("금융비용",           is_div) or _get("이자비용",         is_div),

        # ── 현금흐름표 ──────────────────────────────────────────
        "영업현금흐름": (
            _get("영업활동현금흐름", "CF")
            or _get("영업활동 현금흐름", "CF")
        ),
        # 유형자산취득은 CF에 음수로 기록됨 → 절댓값으로 저장
        # 표준 코드(account_id)를 함께 넘겨서 공백 깨짐이나 명칭 변동에 상관없이 완벽 추적
        "유형자산취득": abs(
            _get("유형자산의 취득", "CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities") 
            or _get("유형자산취득", "CF") 
            or 0
        ),
    }

    # None을 0.0으로 변환 (계산 시 ZeroDivisionError 방지)
    return {k: v if v is not None else 0.0 for k, v in result.items()}


@tool
def get_financial_statements(corp_code: str, year: int) -> dict:
    """DART에서 corp_code 기업의 year 연도 재무제표를 가져와
    표준 계정과목 dict로 반환한다."""
    dart = _get_dart()
    # 회사명 조회
    corp_info = dart.company(corp_code)
    corp_name = corp_info["corp_name"] if corp_info is not None else corp_code

    fs = dart.finstate_all(corp_code, year)
    if fs is None or fs.empty:
        raise ValueError(f"corp_code={corp_code}, year={year} 재무제표 없음")

    result = _normalize_accounts(fs)
    result["회사명"] = corp_name

    audit_opinion, is_external_audit = _fetch_audit_opinion(corp_code, year)
    result["audit_opinion"] = audit_opinion
    result["is_external_audit"] = is_external_audit

    logger.info(
        "get_financial_statements corp_code=%s year=%s audit_opinion=%s is_external_audit=%s",
        corp_code, year, audit_opinion, is_external_audit,
    )
    return result


@tool
def calc_financial_ratios(fs: dict) -> dict:
    """재무제표 dict에서 안정성·활동성·수익성·현금흐름 비율을 계산한다.

    안정성: 부채비율, 유동비율, 당좌비율, 차입금의존도, 이자보상배율
    활동성: 매출채권회전율, 총자산회전율, 매입채무회전율
    수익성: ROA, 영업이익률, 매출원가율
    현금흐름: OCF/매출액, OCF/당기순이익, FCF, FCF/매출액
    """
    total_assets  = max(fs["총자산"],    1)
    equity        = max(fs["자본총계"],  1)
    current_liab  = max(fs["유동부채"], 1)
    revenue       = max(fs["매출액"],    1)
    net_income    = fs["당기순이익"]
    op_income     = fs["영업이익"]
    interest_exp  = fs["이자비용"]
    ocf           = fs["영업현금흐름"]
    capex         = fs["유형자산취득"]   # 0.0이면 데이터 없음

    # 차입금 총계
    total_borrow = fs["단기차입금"] + fs["유동성장기차입금"] + fs["장기차입금"] + fs["사채"]

    # FCF = OCF - CapEx (CapEx가 0원일 때도 정상 연산되도록 수식 교정, None이 아닐 때만 계산)
    fcf = (ocf - capex) if capex is not None else None

    # 당좌자산 = 유동자산 - 재고자산
    quick_assets = fs["유동자산"] - fs["재고자산"]

    return {
        # 안정성
        "debt_ratio":        fs["부채총계"] / equity,
        "current_ratio":     fs["유동자산"] / current_liab,
        "quick_ratio":       quick_assets / current_liab,
        "borrow_dep":        total_borrow / total_assets,   # 차입금의존도
        "interest_coverage": op_income / interest_exp if interest_exp > 0 else None,   # 이자보상배율

        # 활동성
        "receivable_turnover": revenue / max(fs["매출채권"], 1),
        "asset_turnover":      revenue / total_assets,
        "payable_turnover":    fs["매출원가"] / max(fs["매입채무"], 1),

        # 수익성
        "roa":          net_income / total_assets,
        "op_margin":    op_income  / revenue,
        "cogs_ratio":   fs["매출원가"] / revenue,              # 매출원가율

        # 현금흐름
        "ocf_to_sales":      ocf / revenue,
        "ocf_to_net_income": ocf / net_income if net_income != 0 else None,
        "fcf": fcf if fcf is not None else 0.0,
        # fcf와 revenue가 모두 정상적으로 존재할 때만 계산하고, 아니면 0.0이나 None을 리턴
        "fcf_to_sales":      (fcf / revenue) if (fcf is not None and revenue) else 0.0
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
        "z_prime":    round(z, 3),
        "zone":       zone,
        "components": {
            "X1": round(x1, 4), "X2": round(x2, 4),
            "X3": round(x3, 4), "X4": round(x4, 4), "X5": round(x5, 4),
        },
    }


@tool
def trend_analysis(corp_code: str, years: list[int]) -> dict:
    """최근 3개년 재무비율의 급변 항목을 플래그로 반환.

    YoY 감시 항목:
    - 부채비율 +20%p 이상 급증
    - 영업이익률 -5%p 이상 급락
    - 매출액 -10% 이상 급감
    - 영업현금흐름 음수 전환

    절댓값 플래그:
    - ICR < 1.0 → 위험 / ICR < 1.5 → 주의
    - 부채비율 ≥ 300% → 위험 / ≥ 200% → 주의
    """
    dart = _get_dart()
    history = []
    flags = []

    for year in sorted(years):
        fs_raw = dart.finstate_all(corp_code, year)
        if fs_raw is None or fs_raw.empty:
            flags.append(f"{year}_data_missing")
            continue
        fs = _normalize_accounts(fs_raw)

        revenue    = fs["매출액"]
        net_income = fs["당기순이익"]
        total_assets = fs["총자산"]
        debt_ratio = fs["부채총계"] / max(fs["자본총계"], 1)
        op_margin  = fs["영업이익"] / max(revenue, 1)
        interest_exp = fs["이자비용"]
        icr = fs["영업이익"] / interest_exp if interest_exp > 0 else None

        history.append({
            "year":          year,
            "debt_ratio":    round(debt_ratio, 4),
            "op_margin":     round(op_margin,  4),
            "icr": round(icr, 4) if icr is not None else None,
            "revenue":       revenue,
            "net_income":    net_income,
            "total_assets":  total_assets,
            "ocf":           fs["영업현금흐름"],
        })

    yoy = {
        "debt_ratio":    [],
        "op_margin":     [],
        "revenue_growth":[],
        "asset_growth":  [],
    }

    for i in range(1, len(history)):
        prev, curr = history[i - 1], history[i]
        yr = curr["year"]

        # ── YoY 변화량 계산 ───────────────────────────────────
        debt_chg   = curr["debt_ratio"] - prev["debt_ratio"]
        margin_chg = curr["op_margin"]  - prev["op_margin"]
        rev_growth = (
            (curr["revenue"] - prev["revenue"]) / abs(prev["revenue"])
            if prev["revenue"] != 0 else 0.0
        )
        asset_growth = (
            (curr["total_assets"] - prev["total_assets"]) / abs(prev["total_assets"])
            if prev["total_assets"] != 0 else 0.0
        )

        yoy["debt_ratio"].append(round(debt_chg,    4))
        yoy["op_margin"].append(round(margin_chg,   4))
        yoy["revenue_growth"].append(round(rev_growth,  4))
        yoy["asset_growth"].append(round(asset_growth,  4))

        # ── YoY 플래그 ────────────────────────────────────────
        if debt_chg >= 0.20:
            flags.append(f"{yr}_debt_ratio_spike_+{debt_chg:.0%}")
        if margin_chg <= -0.05:
            flags.append(f"{yr}_op_margin_drop_{margin_chg:.0%}")
        if rev_growth <= -0.10:
            flags.append(f"{yr}_revenue_drop_{rev_growth:.0%}")
        if curr["ocf"] < 0:
            flags.append(f"{yr}_negative_operating_cashflow")

    # ── 절댓값 플래그 (최신 연도 기준) ───────────────────────
    if history:
        latest = history[-1]
        yr = latest["year"]

        icr = latest["icr"]
        if icr is not None:
            if icr < 1.0:
                flags.append(f"{yr}_icr_danger_{icr:.2f}")
            elif icr < 1.5:
                flags.append(f"{yr}_icr_caution_{icr:.2f}")

        dr = latest["debt_ratio"]
        if dr >= 3.0:
            flags.append(f"{yr}_debt_ratio_danger_{dr:.0%}")
        elif dr >= 2.0:
            flags.append(f"{yr}_debt_ratio_caution_{dr:.0%}")

    growth_ratios = {}
    if history:
        latest = history[-1]
        prev   = history[-2] if len(history) >= 2 else None

        growth_ratios = {
            "revenue_growth": yoy["revenue_growth"][-1] if yoy["revenue_growth"] else None, # 매출액증가율 (최신년도 YoY)
            "asset_growth":   yoy["asset_growth"][-1]   if yoy["asset_growth"]   else None, # 총자산증가율
            "net_income_growth": (                                                          # 순이익증가율 (history에서 계산)
                round((latest["net_income"] - prev["net_income"]) / abs(prev["net_income"]), 4)
                if prev and prev["net_income"] != 0 else None
            ),
            "tangible_asset_growth": None, # 유형자산증가율 (fs에 유형자산 있으면 산출) # history에 유형자산 미포함 — 추후 확장
        }

    return {"flags": flags, "yoy": yoy, "history": history, "growth_ratios": growth_ratios}


@tool
def apply_risk_filters(fs: dict, history: list[dict]) -> dict:
    """재무 데이터 기반 신용등급 상한(grade_cap)을 결정하는 리스크 필터.

    필터 우선순위 (높을수록 강한 제약):
    1. 자기자본 전액잠식 (단, 3년 연속 당기순이익 흑자 시 면제) → grade_cap: CCC
    2. 자기자본비율 10% 이하 (영세·개인사업자 제외)             → grade_cap: CCC
    3. 감사의견 부적정 또는 거절 (외감기업 전용)                 → grade_cap: CCC
    4. 당기순손실 2개년 연속                                    → grade_cap: B
    5. 매출액 3억 미만                                          → grade_cap: B+
    6. 매출액 20억 미만                                         → grade_cap: BB+

    복수 필터 발동 시 가장 강한 제약(낮은 등급) 적용.
    grade_cap은 절대 상한이며 실제 최종 등급은 XAI/Decision Agent에서 산출.
    재무제표 없는 기업은 get_financial_statements에서 ValueError로 차단됨.
    """
    # 등급 순서 (낮은 인덱스 = 더 강한 제약)
    grade_order = [
        "CCC",
        "B",
        "B+",
        "BB-",
        "BB",
        "BB+",
        "BBB-",
        "BBB",
        "BBB+",
        "A-",
        "A",
        "A+",
        "AA-",
        "AA",
        "AA+",
        "AAA",
    ]
    
    # 발동된 필터들의 등급 상한 결정
    filter_cap = {
        "완전자본잠식":           "CCC",
        "자기자본비율_10%이하":    "CCC",
        "감사의견_부적정또는거절":  "CCC",
        "당기순손실_2년연속":      "B",
        "매출액_3억미만":          "B+",
        "매출액_20억미만":         "BB+",
    }

    triggered: list[str] = []
    detail: dict[str, str] = {}

    equity            = fs.get("자본총계", 0.0)
    total_assets      = fs.get("총자산",   0.0)
    revenue           = fs.get("매출액",   0.0)
    audit_opinion     = fs.get("audit_opinion", None)
    is_external_audit = fs.get("is_external_audit", False)
    is_exempt_equity  = (
        fs.get("is_small_enterprise", False)
        or fs.get("is_individual", False)
    )

    equity_ratio = equity / total_assets if total_assets > 0 else 0.0

    # 필터 1: 자기자본 전액잠식 (3년 연속 흑자 시 면제)
    if equity <= 0:
        three_year_profit = (
            len(history) >= 3
            and all(h.get("net_income", 0) > 0 for h in history[-3:])
        )
        if three_year_profit:
            detail["완전자본잠식_면제"] = (
                f"자본총계={equity:,.0f}원이나 "
                f"최근 3개년({', '.join(str(h['year']) for h in history[-3:])}) "
                "연속 당기순이익 흑자로 CCC 필터 면제"
            )
        else:
            triggered.append("완전자본잠식")
            profit_years = [h["year"] for h in history if h.get("net_income", 0) > 0]
            detail["완전자본잠식"] = (
                f"자본총계={equity:,.0f}원 (≤ 0), "
                f"3년 연속 흑자 미충족 (흑자 연도: {profit_years if profit_years else '없음'})"
            )

    # 필터 2: 자기자본비율 10% 이하 (영세·개인사업자 제외)
    if 0 < equity_ratio <= 0.10 and not is_exempt_equity:
        triggered.append("자기자본비율_10%이하")
        detail["자기자본비율_10%이하"] = f"자기자본비율={equity_ratio:.1%}"

    # 필터 3: 감사의견 부적정 또는 거절 (외감기업 전용)
    if is_external_audit and audit_opinion in ("부적정", "거절"):
        triggered.append("감사의견_부적정또는거절")
        detail["감사의견_부적정또는거절"] = f"감사의견={audit_opinion} (외감기업)"

    # 필터 4: 당기순손실 2개년 연속
    if len(history) >= 2:
        recent_two = history[-2:]
        if all(h.get("net_income", 0) < 0 for h in recent_two):
            years_str = ", ".join(str(h["year"]) for h in recent_two)
            triggered.append("당기순손실_2년연속")
            detail["당기순손실_2년연속"] = f"{years_str}년 연속 순손실"

    # 필터 5: 매출액 3억 미만
    if 0 < revenue < 300_000_000:
        triggered.append("매출액_3억미만")
        detail["매출액_3억미만"] = f"매출액={revenue / 1e8:.2f}억원"

    # 필터 6: 매출액 20억 미만 (필터 5 미발동 시에만 의미 있음)
    elif 0 < revenue < 2_000_000_000:
        triggered.append("매출액_20억미만")
        detail["매출액_20억미만"] = f"매출액={revenue / 1e8:.2f}억원"

    # 가장 강한 제약(낮은 등급) 선택
    grade_cap = None
    for f in triggered:
        cap = filter_cap[f]
        if grade_cap is None or grade_order.index(cap) < grade_order.index(grade_cap):
            grade_cap = cap

    return {
        "grade_cap":          grade_cap,
        "triggered_filters":  triggered,
        "filter_detail":      detail,
    }
