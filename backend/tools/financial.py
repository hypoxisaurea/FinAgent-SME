import logging

import pandas as pd
from backend.common.env import load_backend_env
from backend.integrations import dart_client
from langchain_core.tools import tool

load_backend_env()

logger = logging.getLogger(__name__)
OpenDartReader = dart_client.OpenDartReader
_LOW_QUALITY_RATIO_LIMIT = 100.0


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

        # ── 현금성 자산 (EBITDA/유동성 분석용) ───────────────────
        "현금및현금성자산": (
            _get("현금및현금성자산", "BS")
            or _get("현금및현금성자산및단기금융상품", "BS")
        ),
        "단기금융상품": (
            _get("단기금융상품",   "BS")
            or _get("단기투자자산", "BS")
            or _get("단기금융자산", "BS")
        ),

        # ── 상각비 (EBITDA 계산용) ────────────────────────────────
        # IS/CIS 우선, 없으면 CF 비현금 항목에서 폴백
        "감가상각비": (
            _get("감가상각비",           is_div)
            or _get("유형자산감가상각비", is_div)
            or _get("감가상각비",           "CF")
        ),
        "무형자산상각비": (
            _get("무형자산상각비", is_div)
            or _get("무형자산상각비", "CF")
        ),
    }

    # None을 0.0으로 변환 (계산 시 ZeroDivisionError 방지)
    return {k: v if v is not None else 0.0 for k, v in result.items()}


# ---------------------------------------------------------------------------
# 기업 규모 분류 — is_individual / is_small_enterprise
# ---------------------------------------------------------------------------

# DART corp_cls 필드에서 법인으로 분류되는 코드
# Y=유가증권, K=코스닥, N=코넥스, E=기타(외감기업)
_CORPORATE_CORP_CLS: frozenset[str] = frozenset({"Y", "K", "N", "E"})

# 소기업 기준 연평균 매출액 상한 (원)
# 출처: 중소기업기본법 시행령 별표 3 (2021.12.28 개정)
# induty_code 앞 2자리(KSIC 세분류 첫 두 자리) → 매출액 상한
_SMALL_ENTERPRISE_REVENUE_LIMIT: dict[str, int] = {
    # A 농림어업 (01, 03) — 50억
    "01": 5_000_000_000, "03": 5_000_000_000,
    # B 광업 (05~08) — 120억
    "05": 12_000_000_000, "06": 12_000_000_000,
    "07": 12_000_000_000, "08": 12_000_000_000,
    # C 제조업 (10~33) — 120억
    **{str(i).zfill(2): 12_000_000_000 for i in range(10, 34)},
    # D35 전기·가스·증기 — 30억 (법령 별도 항목 없음, 기타 기준 적용)
    "35": 3_000_000_000,
    # E 수도·하수·폐기물처리 (37~39) — 30억
    "37": 3_000_000_000, "38": 3_000_000_000, "39": 3_000_000_000,
    # F 건설업 (41~42) — 120억
    "41": 12_000_000_000, "42": 12_000_000_000,
    # G 도매·소매업 (45~47) — 50억
    "45": 5_000_000_000, "46": 5_000_000_000, "47": 5_000_000_000,
    # H 운수·창고업 (49~52) — 120억
    "49": 12_000_000_000, "50": 12_000_000_000,
    "51": 12_000_000_000, "52": 12_000_000_000,
    # I 숙박·음식점업 (55~56) — 10억
    "55": 1_000_000_000, "56": 1_000_000_000,
    # J 정보통신업 (58~63) — 50억
    "58": 5_000_000_000, "59": 5_000_000_000, "60": 5_000_000_000,
    "61": 5_000_000_000, "62": 5_000_000_000, "63": 5_000_000_000,
    # L 부동산업 (68) — 30억
    "68": 3_000_000_000,
    # M 전문·과학·기술서비스업 (71~73) — 30억
    "71": 3_000_000_000, "72": 3_000_000_000, "73": 3_000_000_000,
    # N 사업시설관리·지원·임대 (74~76) — 30억
    "74": 3_000_000_000, "75": 3_000_000_000, "76": 3_000_000_000,
    # P 교육서비스업 (85) — 30억
    "85": 3_000_000_000,
    # Q 보건·사회복지서비스업 (86~87) — 30억
    "86": 3_000_000_000, "87": 3_000_000_000,
    # R 예술·스포츠·여가서비스업 (90~91) — 10억
    "90": 1_000_000_000, "91": 1_000_000_000,
    # S 개인서비스업 (95~96) — 10억
    "95": 1_000_000_000, "96": 1_000_000_000,
}
_DEFAULT_SMALL_ENTERPRISE_REVENUE_LIMIT: int = 3_000_000_000  # 30억 (미분류 기본)


def _is_individual_business(corp_cls: str) -> bool:
    """DART 법인구분(corp_cls) 기준 개인사업자 여부를 판별한다.

    Y(유가증권), K(코스닥), N(코넥스), E(외감기업)은 모두 법인이므로 False.
    DART corp_code가 존재하는 기업은 대부분 법인이므로, corp_cls 미수집 시
    개인사업자가 아닌 법인으로 간주 (보수적 분류).
    """
    cleaned = corp_cls.strip()
    if not cleaned:
        return False  # corp_cls 미수집 시 법인으로 간주
    return cleaned not in _CORPORATE_CORP_CLS


def _is_small_enterprise(revenue: float, induty_code: str) -> bool:
    """중소기업기본법 시행령 별표 3 기준으로 소기업 여부를 판별한다.

    induty_code 앞 2자리를 KSIC 분류로 사용해 업종별 연평균 매출액 상한과 비교한다.
    매출액이 0 이하이거나 induty_code를 파싱할 수 없으면 False를 반환한다.
    """
    if not revenue or revenue <= 0:
        return False
    prefix = (induty_code or "").strip()[:2]
    limit = _SMALL_ENTERPRISE_REVENUE_LIMIT.get(prefix, _DEFAULT_SMALL_ENTERPRISE_REVENUE_LIMIT)
    return revenue <= limit


@tool
def get_financial_statements(corp_code: str, year: int) -> dict:
    """DART에서 corp_code 기업의 year 연도 재무제표를 가져와
    표준 계정과목 dict로 반환한다."""
    dart = _get_dart()
    # 회사명·업종코드·법인구분 조회
    corp_info = dart.company(corp_code)
    corp_name   = corp_info["corp_name"]                   if corp_info is not None else corp_code
    induty_code = str(corp_info.get("induty_code", ""))    if corp_info is not None else ""
    corp_cls    = str(corp_info.get("corp_cls",    ""))    if corp_info is not None else ""

    fs = dart.finstate_all(corp_code, year)
    if fs is None or fs.empty:
        raise ValueError(f"corp_code={corp_code}, year={year} 재무제표 없음")

    result = _normalize_accounts(fs)
    result["회사명"] = corp_name

    audit_opinion, is_external_audit = _fetch_audit_opinion(corp_code, year)
    result["audit_opinion"]      = audit_opinion
    result["is_external_audit"]  = is_external_audit
    result["is_individual"]      = _is_individual_business(corp_cls)
    result["is_small_enterprise"] = _is_small_enterprise(result.get("매출액", 0.0), induty_code)

    logger.info(
        "get_financial_statements corp_code=%s year=%s corp_cls=%s induty_code=%s "
        "audit_opinion=%s is_external_audit=%s is_individual=%s is_small_enterprise=%s",
        corp_code, year, corp_cls, induty_code,
        audit_opinion, is_external_audit,
        result["is_individual"], result["is_small_enterprise"],
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
    interest_source_account = fs.get("이자비용_원본계정")
    interest_quality = str(fs.get("이자비용_품질") or "").strip().lower() or None
    ocf           = fs["영업현금흐름"]
    capex         = fs["유형자산취득"]   # 0.0이면 데이터 없음

    # 차입금 총계
    total_borrow = fs["단기차입금"] + fs["유동성장기차입금"] + fs["장기차입금"] + fs["사채"]

    # EBITDA 구성 요소 — .get() 사용: providers.py 업데이트 전까지는 DB 경로에서 0.0으로 근사
    depreciation = fs.get("감가상각비",       0.0)
    amortization = fs.get("무형자산상각비",   0.0)
    cash         = fs.get("현금및현금성자산", 0.0)
    short_fin    = fs.get("단기금융상품",     0.0)

    ebitda   = op_income + depreciation + amortization
    net_debt = total_borrow - (cash + short_fin)

    # FCF = OCF - CapEx (CapEx가 0원일 때도 정상 연산되도록 수식 교정, None이 아닐 때만 계산)
    fcf = (ocf - capex) if capex is not None else None

    # 당좌자산 = 유동자산 - 재고자산
    quick_assets = fs["유동자산"] - fs["재고자산"]

    ratio_note: str | None = None
    interest_for_ratio = interest_exp
    estimated_interest_ratio = False
    if interest_quality == "low":
        estimated_interest_ratio = True
        interest_for_ratio = abs(interest_exp)
        ratio_note = (
            f"이자보상배율 관련 지표는 {interest_source_account or '금융원가'} 기준 "
            "추정 이자비용으로 산출했습니다."
        )

    interest_coverage = (
        op_income / interest_for_ratio if interest_for_ratio > 0 else None
    )
    ebitda_to_interest = (
        ebitda / interest_for_ratio
        if (ebitda > 0 and interest_for_ratio > 0)
        else None
    )

    if estimated_interest_ratio:
        if interest_coverage is not None and abs(interest_coverage) > _LOW_QUALITY_RATIO_LIMIT:
            interest_coverage = None
            ratio_note = (
                f"{interest_source_account or '금융원가'} 기준 추정치의 왜곡 가능성이 커 "
                "이자보상배율 산출을 제외했습니다."
            )
        if ebitda_to_interest is not None and abs(ebitda_to_interest) > _LOW_QUALITY_RATIO_LIMIT:
            ebitda_to_interest = None
            ratio_note = (
                f"{interest_source_account or '금융원가'} 기준 추정치의 왜곡 가능성이 커 "
                "EBITDA/이자비용 산출을 제외했습니다."
            )

    return {
        # 안정성
        "debt_ratio":        fs["부채총계"] / equity,
        "current_ratio":     fs["유동자산"] / current_liab,
        "quick_ratio":       quick_assets / current_liab,
        "borrow_dep":        total_borrow / total_assets,   # 차입금의존도
        "interest_coverage": interest_coverage,   # 이자보상배율

        # 활동성
        "receivable_turnover": revenue / max(fs["매출채권"], 1),
        "asset_turnover":      revenue / total_assets,
        "payable_turnover":    fs["매출원가"] / max(fs["매입채무"], 1),

        # 수익성
        "roa":          net_income / total_assets,
        "op_margin":    op_income  / revenue,
        "net_margin":   net_income / revenue,                  # 순이익률
        "cogs_ratio":   fs["매출원가"] / revenue,              # 매출원가율

        # 현금흐름
        "ocf_to_sales":      ocf / revenue,
        "ocf_to_net_income": ocf / net_income if net_income != 0 else None,
        "fcf": fcf if fcf is not None else 0.0,
        # fcf와 revenue가 모두 정상적으로 존재할 때만 계산하고, 아니면 0.0이나 None을 리턴
        "fcf_to_sales":      (fcf / revenue) if (fcf is not None and revenue) else 0.0,

        # EBITDA (ebitda ≤ 0이면 비율 무의미 → None)
        "ebitda":             ebitda,
        "ebitda_margin":      ebitda / revenue,
        "net_debt_to_ebitda": net_debt / ebitda if ebitda > 0 else None,
        "ebitda_to_interest": ebitda_to_interest,
        "interest_expense_source_account": interest_source_account,
        "interest_expense_quality": interest_quality,
        "interest_ratio_estimated": estimated_interest_ratio,
        "interest_ratio_note": ratio_note,
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
