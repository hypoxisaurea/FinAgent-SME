"""
test_financial_industry_agents_tools.py
========================================
테스트 범위:
  [A] 기존 도구 회귀 테스트 (get_financial_statements / calc_financial_ratios /
                              calc_altman_z_prime / trend_analysis)
  [B] apply_risk_filters 보완 테스트 (이번 수정의 핵심)
       B-1  정상 기업 → 필터 없음
       B-2  완전자본잠식 + 3년 연속 흑자 → CCC 면제
       B-3  완전자본잠식 + 흑자 미충족   → CCC
       B-4  자기자본비율 8%              → CCC
       B-5  감사의견 부적정 + 외감       → CCC
       B-6  감사의견 부적정 + 비외감     → 미발동
       B-7  감사의견 거절   + 외감       → CCC
       B-8  당기순손실 2년 연속          → B
       B-9  매출 1억 (3억 미만)          → B+
       B-10 매출 15억 (20억 미만)        → BB+
       B-11 복수 필터 (감사의견CCC + 순손실B) → CCC 우선
  [C] get_financial_statements — audit_opinion / is_external_audit 주입 확인
  [D] 기존 industry 도구 회귀 테스트
"""

import sys
import os

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend_env import load_backend_env
from pathlib import Path
load_backend_env(env_path=Path(BACKEND_DIR) / ".env")

from agents.financial_analyst.financial_tools import (
    get_financial_statements,
    calc_financial_ratios,
    calc_altman_z_prime,
    trend_analysis,
    apply_risk_filters,
)
from agents.industry_analyst.industry_tools import (
    map_corp_to_ksic,
    get_industry_avg_ratios,
    get_industry_outlook,
    get_business_cycle,
    get_macro_indicators,
)

# ── 공통 테스트 대상 ─────────────────────────────────────────────────────────
CORP_CODE = "01074862"   # 메가스터디교육(주)
YEAR      = 2024
YEARS     = [2022, 2023, 2024]

# ── 출력 헬퍼 ────────────────────────────────────────────────────────────────
PASS = 0
FAIL = 0

def sep(title: str):
    print(f"\n{'='*60}\n{title}\n{'='*60}")

def ok(msg: str = ""):
    global PASS
    PASS += 1
    print(f"  ✅ PASS  {msg}")

def ng(msg: str = ""):
    global FAIL
    FAIL += 1
    print(f"  ❌ FAIL  {msg}")

def check(condition: bool, label: str):
    if condition:
        ok(label)
    else:
        ng(label)

# ════════════════════════════════════════════════════════════════════════════
# [A] 기존 도구 회귀 테스트
# ════════════════════════════════════════════════════════════════════════════
sep("[A] 기존 도구 회귀 테스트 — DART API 호출 포함")

fs = None
ratios = None
trend = None

# A-1. get_financial_statements
print("\n[A-1] get_financial_statements")
try:
    fs = get_financial_statements.invoke({"corp_code": CORP_CODE, "year": YEAR})
    check(isinstance(fs, dict),           "반환값이 dict")
    check("매출액" in fs,                 "매출액 키 존재")
    check("자본총계" in fs,               "자본총계 키 존재")
    check("audit_opinion" in fs,          "audit_opinion 키 존재 (신규)")
    check("is_external_audit" in fs,      "is_external_audit 키 존재 (신규)")
    check(isinstance(fs["is_external_audit"], bool), "is_external_audit 가 bool")
    print(f"     audit_opinion    = {fs.get('audit_opinion')}")
    print(f"     is_external_audit= {fs.get('is_external_audit')}")
except Exception as e:
    ng(f"get_financial_statements 예외: {e}")

# A-2. calc_financial_ratios
print("\n[A-2] calc_financial_ratios")
if fs:
    try:
        ratios = calc_financial_ratios.invoke({"fs": fs})
        check(isinstance(ratios, dict),        "반환값이 dict")
        check("debt_ratio" in ratios,          "debt_ratio 존재")
        check("op_margin" in ratios,           "op_margin 존재")
        check(len(ratios) >= 15,               "15개 이상 비율 반환")
        print(f"     debt_ratio = {ratios.get('debt_ratio'):.4f}")
        print(f"     op_margin  = {ratios.get('op_margin'):.4f}")
    except Exception as e:
        ng(f"calc_financial_ratios 예외: {e}")
else:
    ng("fs 없음 — 스킵")

# A-3. calc_altman_z_prime
print("\n[A-3] calc_altman_z_prime")
if fs:
    try:
        z = calc_altman_z_prime.invoke({"fs": fs})
        check(isinstance(z, dict),                          "반환값이 dict")
        check("z_prime" in z,                              "z_prime 존재")
        check(z.get("zone") in ("Safe","Grey","Distress"), "zone 값이 유효")
        print(f"     Z' = {z.get('z_prime')}  →  {z.get('zone')}")
    except Exception as e:
        ng(f"calc_altman_z_prime 예외: {e}")
else:
    ng("fs 없음 — 스킵")

# A-4. trend_analysis + growth_ratios 신규 확인
print("\n[A-4] trend_analysis — growth_ratios 섹션 포함")
try:
    trend = trend_analysis.invoke({"corp_code": CORP_CODE, "years": YEARS})
    check(isinstance(trend, dict),              "반환값이 dict")
    check("flags"   in trend,                  "flags 키 존재")
    check("yoy"     in trend,                  "yoy 키 존재")
    check("history" in trend,                  "history 키 존재")
    check("growth_ratios" in trend,            "growth_ratios 키 존재 (신규)")
    if "growth_ratios" in trend:
        gr = trend["growth_ratios"]
        check("revenue_growth"    in gr,       "  revenue_growth 존재")
        check("asset_growth"      in gr,       "  asset_growth 존재")
        check("net_income_growth" in gr,       "  net_income_growth 존재")
        check("tangible_asset_growth" in gr,   "  tangible_asset_growth 존재")
        print(f"     revenue_growth    = {gr.get('revenue_growth')}")
        print(f"     asset_growth      = {gr.get('asset_growth')}")
        print(f"     net_income_growth = {gr.get('net_income_growth')}")
except Exception as e:
    ng(f"trend_analysis 예외: {e}")

# ════════════════════════════════════════════════════════════════════════════
# [B] apply_risk_filters 보완 테스트 (mock 데이터, API 호출 없음)
# ════════════════════════════════════════════════════════════════════════════
sep("[B] apply_risk_filters 보완 테스트 — mock 데이터")

def run_filter_case(label: str, fs_mock: dict, history_mock: list,
                    expected_cap, expected_filters: list):
    print(f"\n[{label}]")
    try:
        result = apply_risk_filters.invoke({"fs": fs_mock, "history": history_mock})
        cap       = result["grade_cap"]
        triggered = result["triggered_filters"]
        detail    = result["filter_detail"]

        check(cap == expected_cap,
              f"grade_cap = {cap!r}  (기대: {expected_cap!r})")
        for f in expected_filters:
            check(f in triggered,
                  f"'{f}' triggered 에 포함")
        if not expected_filters:
            check(triggered == [],
                  f"triggered 빈 리스트  (실제: {triggered})")

        # 면제 케이스는 detail 에 면제 키가 있어야 함
        if expected_cap is None and cap is None and "완전자본잠식_면제" in detail:
            ok("완전자본잠식_면제 detail 키 존재")

    except Exception as e:
        ng(f"예외 발생: {e}")

# 공통 mock — 정상 수치
BASE_FS = {
    "자본총계": 500_000_000,
    "총자산":  1_000_000_000,
    "매출액":  5_000_000_000,
    "audit_opinion": None,
    "is_external_audit": False,
    "is_small_enterprise": False,
    "is_individual": False,
}
HISTORY_OK = [
    {"year": 2022, "net_income":  100_000_000},
    {"year": 2023, "net_income":  200_000_000},
    {"year": 2024, "net_income":  300_000_000},
]
HISTORY_LOSS2 = [
    {"year": 2023, "net_income": -100_000_000},
    {"year": 2024, "net_income": -200_000_000},
]

# B-1 정상 기업
run_filter_case(
    "B-1 정상 기업 → 필터 없음",
    BASE_FS, HISTORY_OK,
    expected_cap=None, expected_filters=[],
)

# B-2 완전자본잠식 + 3년 연속 흑자 → CCC 면제
run_filter_case(
    "B-2 완전자본잠식 + 3년 연속 흑자 → CCC 면제",
    {**BASE_FS, "자본총계": -1},
    HISTORY_OK,
    expected_cap=None, expected_filters=[],
)

# B-3 완전자본잠식 + 흑자 미충족 → CCC
run_filter_case(
    "B-3 완전자본잠식 + 흑자 미충족 → CCC",
    {**BASE_FS, "자본총계": -1},
    [{"year": 2022, "net_income": -100},
     {"year": 2023, "net_income":  200},
     {"year": 2024, "net_income":  300}],
    expected_cap="CCC", expected_filters=["완전자본잠식"],
)

# B-4 자기자본비율 8% → CCC
run_filter_case(
    "B-4 자기자본비율 8% → CCC",
    {**BASE_FS, "자본총계": 80_000_000, "총자산": 1_000_000_000},
    [],
    expected_cap="CCC", expected_filters=["자기자본비율_10%이하"],
)

# B-5 감사의견 부적정 + 외감 → CCC
run_filter_case(
    "B-5 감사의견 부적정 + 외감 → CCC",
    {**BASE_FS, "audit_opinion": "부적정", "is_external_audit": True},
    [],
    expected_cap="CCC", expected_filters=["감사의견_부적정또는거절"],
)

# B-6 감사의견 부적정 + 비외감 → 미발동
run_filter_case(
    "B-6 감사의견 부적정 + 비외감 → 필터 미발동",
    {**BASE_FS, "audit_opinion": "부적정", "is_external_audit": False},
    [],
    expected_cap=None, expected_filters=[],
)

# B-7 감사의견 거절 + 외감 → CCC
run_filter_case(
    "B-7 감사의견 거절 + 외감 → CCC",
    {**BASE_FS, "audit_opinion": "거절", "is_external_audit": True},
    [],
    expected_cap="CCC", expected_filters=["감사의견_부적정또는거절"],
)

# B-8 당기순손실 2년 연속 → B
run_filter_case(
    "B-8 당기순손실 2년 연속 → B",
    BASE_FS, HISTORY_LOSS2,
    expected_cap="B", expected_filters=["당기순손실_2년연속"],
)

# B-9 매출 1억 (3억 미만) → B+
run_filter_case(
    "B-9 매출 1억 → B+",
    {**BASE_FS, "매출액": 100_000_000},
    [],
    expected_cap="B+", expected_filters=["매출액_3억미만"],
)

# B-10 매출 15억 (20억 미만) → BB+
run_filter_case(
    "B-10 매출 15억 → BB+",
    {**BASE_FS, "매출액": 1_500_000_000},
    [],
    expected_cap="BB+", expected_filters=["매출액_20억미만"],
)

# B-11 복수 필터 — 감사의견CCC + 순손실B → CCC 우선
run_filter_case(
    "B-11 복수 필터 (감사의견CCC + 순손실B) → CCC 우선",
    {**BASE_FS, "audit_opinion": "거절", "is_external_audit": True},
    HISTORY_LOSS2,
    expected_cap="CCC",
    expected_filters=["감사의견_부적정또는거절", "당기순손실_2년연속"],
)

# ════════════════════════════════════════════════════════════════════════════
# [C] get_financial_statements — audit 필드 실제 API 검증
# ════════════════════════════════════════════════════════════════════════════
sep("[C] get_financial_statements — audit 필드 실제 API 검증")

print("\n[C-1] 메가스터디교육(주) — 상장사이므로 is_external_audit=True 기대")
if fs:
    check(fs.get("is_external_audit") is True,
          f"is_external_audit=True  (실제: {fs.get('is_external_audit')})")
    check(fs.get("audit_opinion") is not None,
          f"audit_opinion 값 있음  (실제: {fs.get('audit_opinion')!r})")
else:
    ng("fs 없음 — 스킵")

# ════════════════════════════════════════════════════════════════════════════
# [D] industry 도구 회귀 테스트
# ════════════════════════════════════════════════════════════════════════════
sep("[D] industry 도구 회귀 테스트 — DART/ECOS/KOSIS API 호출 포함")

ksic = None
company_ratios = None

# D-1. map_corp_to_ksic
print("\n[D-1] map_corp_to_ksic")
try:
    ksic_result = map_corp_to_ksic.invoke({"corp_code": CORP_CODE})
    ksic = ksic_result if isinstance(ksic_result, str) else ksic_result.get("ksic_code")
    check(ksic is not None,       f"ksic_code 반환: {ksic}")
except Exception as e:
    ng(f"예외: {e}")

# company_ratios 구성 (D-2 입력용)
if ratios and trend and "growth_ratios" in trend:
    company_ratios = {
        "debt_ratio":          ratios["debt_ratio"],
        "current_ratio":       ratios["current_ratio"],
        "op_margin":           ratios["op_margin"],
        "interest_coverage":   ratios["interest_coverage"],
        "borrow_dep":          ratios["borrow_dep"],
        "receivable_turnover": ratios["receivable_turnover"],
        "asset_turnover":      ratios["asset_turnover"],
        "sales_growth":        trend["growth_ratios"]["revenue_growth"],  # ← 수정 후 경로
    }
    print(f"\n     [참고] company_ratios.sales_growth = "
          f"{company_ratios['sales_growth']}  (growth_ratios 경로 확인)")

# D-2. get_industry_avg_ratios
print("\n[D-2] get_industry_avg_ratios")
if ksic:
    try:
        avg = get_industry_avg_ratios.invoke({
            "ksic_code": ksic,
            "year": YEAR,
            "company_ratios": company_ratios,
        })
        check(isinstance(avg, dict),            "반환값이 dict")
        check("peer_comparison" in avg,         "peer_comparison 존재")
        if company_ratios:
            check(avg.get("peer_comparison") is not None,
                  "company_ratios 전달 시 peer_comparison 활성화")
    except Exception as e:
        ng(f"예외: {e}")
else:
    ng("ksic 없음 — 스킵")

# D-3. get_industry_outlook
print("\n[D-3] get_industry_outlook")
if ksic:
    try:
        outlook = get_industry_outlook.invoke({"ksic_code": ksic})
        check(isinstance(outlook, dict),                         "반환값이 dict")
        check(outlook.get("outlook_score") in ("Low","Medium","High"),
              f"outlook_score 유효: {outlook.get('outlook_score')}")
    except Exception as e:
        ng(f"예외: {e}")
else:
    ng("ksic 없음 — 스킵")

# D-4. get_business_cycle
print("\n[D-4] get_business_cycle")
try:
    bc = get_business_cycle.invoke({})
    check(isinstance(bc, dict),   "반환값이 dict")
    check("business_cycle_phase" in bc or "phase" in bc,
          f"경기 국면 키 존재: {list(bc.keys())}")
except Exception as e:
    ng(f"예외: {e}")

# D-5. get_macro_indicators
print("\n[D-5] get_macro_indicators")
try:
    macro = get_macro_indicators.invoke({"ksic_code": ksic or ""})
    check(isinstance(macro, dict),      "반환값이 dict")
    check("base_rate" in macro,         f"base_rate 존재: {macro.get('base_rate')}")
    check("usd_krw"   in macro,         f"usd_krw 존재:   {macro.get('usd_krw')}")
except Exception as e:
    ng(f"예외: {e}")

# ════════════════════════════════════════════════════════════════════════════
# 최종 결과
# ════════════════════════════════════════════════════════════════════════════
sep("최종 결과")
total = PASS + FAIL
print(f"  PASS: {PASS} / {total}")
print(f"  FAIL: {FAIL} / {total}")
if FAIL == 0:
    print("\n  🎉 모든 테스트 통과")
else:
    print(f"\n  ⚠️  {FAIL}개 실패 — 위 ❌ 항목 확인 필요")
    sys.exit(1)
