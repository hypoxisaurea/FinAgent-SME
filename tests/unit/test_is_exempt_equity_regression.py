"""is_exempt_equity 버그 수정 회귀 테스트 (4개 케이스)

검증 대상: apply_risk_filters() 내 filter 2
  "자기자본비율 10% 이하 → CCC (영세·개인사업자 제외)"

is_exempt_equity = is_small_enterprise OR is_individual

※ filter 1(완전자본잠식)은 equity ≤ 0 조건이며 is_exempt_equity와 무관합니다.
  is_exempt_equity가 실제로 작동하는 filter 2는 0 < equity_ratio ≤ 0.10 조건이므로
  케이스는 "자기자본비율 10% 이하, 자본 양수" 상황으로 설정합니다.
"""

from backend.tools.financial import apply_risk_filters


# 공통 재무 기반값: 총자산 10억, 자기자본 5000만 → 자기자본비율 5% (filter 2 발동)
_BASE_FS: dict = {
    "자본총계": 50_000_000.0,       # 5000만 원 (양수)
    "총자산":   1_000_000_000.0,    # 10억 원
    "매출액":   500_000_000.0,      # 5억 원 (도소매 소기업 상한 50억 이하)
    "audit_opinion":    None,
    "is_external_audit": False,
    "is_small_enterprise": False,
    "is_individual":       False,
}


def _call(fs: dict) -> dict:
    return apply_risk_filters.invoke({"fs": fs, "history": []})


class TestIsExemptEquityRegression:
    """filter 2 (자기자본비율 10% 이하) 면제 로직 회귀 검증"""

    def test_case1_regular_corp_ccc_triggered(self):
        """케이스 1: 일반 상장법인 (is_small=False, is_individual=False)
        → 자기자본비율 5% → filter 2 발동 → CCC"""
        fs = {**_BASE_FS, "is_small_enterprise": False, "is_individual": False}
        result = _call(fs)
        assert "자기자본비율_10%이하" in result["triggered_filters"]
        assert result["grade_cap"] == "CCC"

    def test_case2_small_enterprise_exempt(self):
        """케이스 2: 소기업 (is_small_enterprise=True)
        → filter 2 면제 → "자기자본비율_10%이하" 미발동"""
        fs = {**_BASE_FS, "is_small_enterprise": True, "is_individual": False}
        result = _call(fs)
        assert "자기자본비율_10%이하" not in result["triggered_filters"]

    def test_case3_individual_business_exempt(self):
        """케이스 3: 개인사업자 (is_individual=True)
        → filter 2 면제 → "자기자본비율_10%이하" 미발동"""
        fs = {**_BASE_FS, "is_small_enterprise": False, "is_individual": True}
        result = _call(fs)
        assert "자기자본비율_10%이하" not in result["triggered_filters"]

    def test_case4_empty_corp_cls_large_revenue_ccc_not_exempt(self):
        """케이스 4 [CRITICAL]: corp_cls 빈 값 + 매출액 소기업 상한 초과 → CCC 유지

        수정 후 _is_individual_business("")는 False를 반환 (보수적 분류).
        따라서 is_individual=False, is_small_enterprise=False → is_exempt_equity=False
        → filter 2 발동 → "자기자본비율_10%이하" triggered → CCC.
        """
        from backend.tools.financial import _is_individual_business

        # 수정된 함수가 빈 corp_cls를 법인으로 간주(False)하는지 직접 검증
        assert _is_individual_business("") is False, (
            "_is_individual_business('') 이 True를 반환 — Option A 수정이 적용되지 않음"
        )

        # 수정된 분류 결과(is_individual=False)로 apply_risk_filters 검증
        fs = {
            **_BASE_FS,
            "매출액":              50_000_000_000.0,  # 500억 — 소기업 상한 초과
            "is_small_enterprise": False,              # 매출 크므로 소기업 아님
            "is_individual":       False,              # _is_individual_business("") 수정 후 결과
        }
        result = _call(fs)
        assert "자기자본비율_10%이하" in result["triggered_filters"]
        assert result["grade_cap"] == "CCC"
