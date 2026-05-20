"""
K-Credit Agent 도구별 테스트 스크립트
실행: python test_agents.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))

load_dotenv(PROJECT_ROOT / "backend" / ".env")

CORP_CODE = "01074862"
YEAR      = 2024
YEARS     = [2022, 2023, 2024]

# ============================================================
# Financial Agent
# ============================================================
from agents.financial_analyst.financial_tools import (
    get_financial_statements,
    calc_financial_ratios,
    calc_altman_z_prime,
    trend_analysis,
    apply_risk_filters,
)

def sep(title): print(f"\n{'='*50}\n{title}\n{'='*50}")

# ── 1. get_financial_statements ──────────────────────────────
sep("1. get_financial_statements")
try:
    fs = get_financial_statements.invoke({"corp_code": CORP_CODE, "year": YEAR})
    print("✅ 성공")
    for k, v in fs.items():
        print(f"  {k}: {v:,.0f}" if isinstance(v, float) else f"  {k}: {v}")
except Exception as e:
    print(f"❌ 실패: {e}")
    fs = None

# ── 2. calc_financial_ratios ─────────────────────────────────
sep("2. calc_financial_ratios")
if fs:
    try:
        ratios = calc_financial_ratios.invoke({"fs": fs})
        print("✅ 성공")
        for k, v in ratios.items():
            print(f"  {k}: {round(v, 4) if v is not None else 'None'}")
    except Exception as e:
        print(f"❌ 실패: {e}")
        ratios = None
else:
    print("⏭️  fs 없음, 스킵")
    ratios = None

# ── 3. calc_altman_z_prime ───────────────────────────────────
sep("3. calc_altman_z_prime")
if fs:
    try:
        z = calc_altman_z_prime.invoke({"fs": fs})
        print("✅ 성공")
        print(f"  Z' = {z['z_prime']}  →  {z['zone']}")
        print(f"  구성요소: {z['components']}")
    except Exception as e:
        print(f"❌ 실패: {e}")
else:
    print("⏭️  스킵")

# ── 4. trend_analysis ────────────────────────────────────────
sep("4. trend_analysis")
try:
    trend = trend_analysis.invoke({"corp_code": CORP_CODE, "years": YEARS})
    print("✅ 성공")
    print(f"  flags: {trend['flags']}")
    print(f"  yoy:   {trend['yoy']}")
    for h in trend['history']:
        print(f"  [{h['year']}] 부채비율={h['debt_ratio']:.2%}, 영업이익률={h['op_margin']:.2%}, ICR={h['icr']:.2f}")
except Exception as e:
    print(f"❌ 실패: {e}")
    trend = None

# ── 5. apply_risk_filters ────────────────────────────────────
sep("5. apply_risk_filters")
if fs and trend:
    try:
        rf = apply_risk_filters.invoke({"fs": fs, "history": trend["history"]})
        print("✅ 성공")
        print(f"  grade_cap:         {rf['grade_cap']}")
        print(f"  triggered_filters: {rf['triggered_filters']}")
        print(f"  filter_detail:     {rf['filter_detail']}")
    except Exception as e:
        print(f"❌ 실패: {e}")
else:
    print("⏭️  스킵")

# ============================================================
# Industry Agent
# ============================================================
from agents.industry_analyst.industry_tools import (
    map_corp_to_ksic,
    get_industry_avg_ratios,
    get_industry_outlook,
    get_business_cycle,
    get_macro_indicators,
)

# ── 6. map_corp_to_ksic ──────────────────────────────────────
sep("6. map_corp_to_ksic")
try:
    ksic = map_corp_to_ksic.invoke({"corp_code": CORP_CODE})
    print(f"✅ 성공: {ksic}")
except Exception as e:
    print(f"❌ 실패: {e}")
    ksic = None

# ── 7. get_industry_avg_ratios ───────────────────────────────
sep("7. get_industry_avg_ratios")
if ksic and ratios:
    company_ratios = {
        "debt_ratio":          ratios.get("debt_ratio"),
        "current_ratio":       ratios.get("current_ratio"),
        "op_margin":           ratios.get("op_margin"),
        "interest_coverage":   ratios.get("interest_coverage"),
        "borrow_dep":          ratios.get("borrow_dep"),
        "receivable_turnover": ratios.get("receivable_turnover"),
        "asset_turnover":      ratios.get("asset_turnover"),
        "sales_growth":        trend["yoy"]["revenue_growth"][-1] if trend else None,
    }
    try:
        avg = get_industry_avg_ratios.invoke({
            "ksic_code": ksic,
            "year": YEAR,
            "company_ratios": company_ratios,
        })
        print("✅ 성공")
        for k, v in avg.items():
            if k != "peer_comparison":
                print(f"  {k}: {v}")
        if "peer_comparison" in avg:
            print("  peer_comparison:")
            for k, v in avg["peer_comparison"].items():
                print(f"    {k}: {v}")
    except Exception as e:
        print(f"❌ 실패: {e}")
elif not ksic:
    print("⏭️  ksic 없음, 스킵")
else:
    print("⚠️  ratios 없음 → company_ratios 없이 산업평균만 조회")
    try:
        avg = get_industry_avg_ratios.invoke({"ksic_code": ksic, "year": YEAR})
        print("✅ 성공 (peer_comparison 없음)")
        for k, v in avg.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"❌ 실패: {e}")

# ── 8. get_industry_outlook ──────────────────────────────────
sep("8. get_industry_outlook")
if ksic:
    try:
        outlook = get_industry_outlook.invoke({"ksic_code": ksic})
        print("✅ 성공")
        for k, v in outlook.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"❌ 실패: {e}")
else:
    print("⏭️  스킵")

# ── 9. get_business_cycle ────────────────────────────────────
sep("9. get_business_cycle")
try:
    bc = get_business_cycle.invoke({})
    print("✅ 성공")
    for k, v in bc.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"❌ 실패: {e}")

# ── 10. get_macro_indicators ─────────────────────────────────
sep("10. get_macro_indicators")
try:
    macro = get_macro_indicators.invoke({"ksic_code": ksic or ""})
    print("✅ 성공")
    for k, v in macro.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"❌ 실패: {e}")

print("\n" + "="*50)
print("테스트 완료")
print("="*50)
