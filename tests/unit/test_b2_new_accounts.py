"""B2 회귀 테스트: _normalize_accounts 4개 신규 계정 + net_margin

검증 항목:
1. 현금및현금성자산 / 단기금융상품 / 감가상각비 / 무형자산상각비 추출
2. 계정이 없는 경우 0.0 기본값
3. calc_financial_ratios에 net_margin 포함 여부
"""
from __future__ import annotations

import pandas as pd
import pytest

from backend.tools.financial import _normalize_accounts, calc_financial_ratios


# ── 헬퍼: 최소한의 finstate_all DataFrame 생성 ────────────────────────────────

def _make_fs(rows: list[dict]) -> pd.DataFrame:
    """sj_div / account_nm / account_id / thstrm_amount 컬럼 DataFrame."""
    return pd.DataFrame(rows, columns=["sj_div", "account_nm", "account_id", "thstrm_amount"])


def _base_rows() -> list[dict]:
    """정상적인 재무제표 골격 (기존 계정만)."""
    return [
        # BS
        {"sj_div": "BS", "account_nm": "유동자산",   "account_id": "", "thstrm_amount": 700_000_000},
        {"sj_div": "BS", "account_nm": "유동부채",   "account_id": "", "thstrm_amount": 400_000_000},
        {"sj_div": "BS", "account_nm": "자산총계",   "account_id": "", "thstrm_amount": 2_000_000_000},
        {"sj_div": "BS", "account_nm": "자본총계",   "account_id": "", "thstrm_amount": 800_000_000},
        {"sj_div": "BS", "account_nm": "부채총계",   "account_id": "", "thstrm_amount": 1_200_000_000},
        {"sj_div": "BS", "account_nm": "이익잉여금", "account_id": "", "thstrm_amount": 150_000_000},
        {"sj_div": "BS", "account_nm": "재고자산",   "account_id": "", "thstrm_amount": 100_000_000},
        {"sj_div": "BS", "account_nm": "매출채권",   "account_id": "", "thstrm_amount": 120_000_000},
        {"sj_div": "BS", "account_nm": "매입채무",   "account_id": "", "thstrm_amount": 90_000_000},
        {"sj_div": "BS", "account_nm": "단기차입금", "account_id": "", "thstrm_amount": 200_000_000},
        {"sj_div": "BS", "account_nm": "유동성장기차입금", "account_id": "", "thstrm_amount": 50_000_000},
        {"sj_div": "BS", "account_nm": "장기차입금", "account_id": "", "thstrm_amount": 300_000_000},
        {"sj_div": "BS", "account_nm": "사채",       "account_id": "", "thstrm_amount": 0},
        {"sj_div": "BS", "account_nm": "유형자산",   "account_id": "", "thstrm_amount": 500_000_000},
        # IS
        {"sj_div": "IS", "account_nm": "매출액",         "account_id": "", "thstrm_amount": 1_200_000_000},
        {"sj_div": "IS", "account_nm": "매출원가",       "account_id": "", "thstrm_amount": 800_000_000},
        {"sj_div": "IS", "account_nm": "영업이익",       "account_id": "", "thstrm_amount": 120_000_000},
        {"sj_div": "IS", "account_nm": "당기순이익(손실)", "account_id": "", "thstrm_amount": 80_000_000},
        {"sj_div": "IS", "account_nm": "금융비용",       "account_id": "", "thstrm_amount": 30_000_000},
        # CF
        {"sj_div": "CF", "account_nm": "영업활동현금흐름", "account_id": "", "thstrm_amount": 100_000_000},
        {"sj_div": "CF", "account_nm": "유형자산의 취득",
         "account_id": "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
         "thstrm_amount": -40_000_000},
    ]


class TestNewAccountsExtraction:
    """4개 신규 계정 추출 정상 케이스."""

    def test_현금및현금성자산_extracted(self):
        rows = _base_rows() + [
            {"sj_div": "BS", "account_nm": "현금및현금성자산", "account_id": "", "thstrm_amount": 50_000_000},
        ]
        result = _normalize_accounts(_make_fs(rows))
        assert result["현금및현금성자산"] == 50_000_000.0

    def test_단기금융상품_extracted(self):
        rows = _base_rows() + [
            {"sj_div": "BS", "account_nm": "단기금융상품", "account_id": "", "thstrm_amount": 30_000_000},
        ]
        result = _normalize_accounts(_make_fs(rows))
        assert result["단기금융상품"] == 30_000_000.0

    def test_감가상각비_from_IS(self):
        rows = _base_rows() + [
            {"sj_div": "IS", "account_nm": "감가상각비", "account_id": "", "thstrm_amount": 20_000_000},
        ]
        result = _normalize_accounts(_make_fs(rows))
        assert result["감가상각비"] == 20_000_000.0

    def test_무형자산상각비_from_IS(self):
        rows = _base_rows() + [
            {"sj_div": "IS", "account_nm": "무형자산상각비", "account_id": "", "thstrm_amount": 5_000_000},
        ]
        result = _normalize_accounts(_make_fs(rows))
        assert result["무형자산상각비"] == 5_000_000.0

    def test_감가상각비_fallback_to_CF(self):
        """IS에 없을 때 CF에서 폴백."""
        rows = _base_rows() + [
            {"sj_div": "CF", "account_nm": "감가상각비", "account_id": "", "thstrm_amount": 15_000_000},
        ]
        result = _normalize_accounts(_make_fs(rows))
        assert result["감가상각비"] == 15_000_000.0

    def test_현금성자산_fallback_alias(self):
        """'현금및현금성자산및단기금융상품' 별칭에서 폴백."""
        rows = _base_rows() + [
            {"sj_div": "BS", "account_nm": "현금및현금성자산및단기금융상품",
             "account_id": "", "thstrm_amount": 70_000_000},
        ]
        result = _normalize_accounts(_make_fs(rows))
        assert result["현금및현금성자산"] == 70_000_000.0


class TestMissingAccountsDefault:
    """계정이 없는 회사 → 0.0 기본값 검증."""

    def test_missing_all_new_accounts_defaults_to_zero(self):
        """4개 신규 계정이 전혀 없는 재무제표 → 모두 0.0."""
        result = _normalize_accounts(_make_fs(_base_rows()))
        assert result["현금및현금성자산"] == 0.0
        assert result["단기금융상품"]     == 0.0
        assert result["감가상각비"]       == 0.0
        assert result["무형자산상각비"]   == 0.0


class TestNetMarginInRatios:
    """net_margin이 calc_financial_ratios 반환값에 포함되는지 검증."""

    def _make_fs_dict(self) -> dict:
        """_normalize_accounts 반환 형태의 dict (calc_financial_ratios 입력)."""
        return {
            "매출액":         1_200_000_000.0,
            "매출원가":       800_000_000.0,
            "영업이익":       120_000_000.0,
            "당기순이익":     80_000_000.0,
            "이자비용":       30_000_000.0,
            "총자산":         2_000_000_000.0,
            "자본총계":       800_000_000.0,
            "부채총계":       1_200_000_000.0,
            "유동자산":       700_000_000.0,
            "유동부채":       400_000_000.0,
            "재고자산":       100_000_000.0,
            "매출채권":       120_000_000.0,
            "매입채무":       90_000_000.0,
            "단기차입금":     200_000_000.0,
            "유동성장기차입금": 50_000_000.0,
            "장기차입금":     300_000_000.0,
            "사채":           0.0,
            "영업현금흐름":   100_000_000.0,
            "유형자산취득":   40_000_000.0,
            "이익잉여금":     150_000_000.0,
            "유형자산":       500_000_000.0,
            # 신규 계정 (0.0 기본값 포함)
            "현금및현금성자산": 50_000_000.0,
            "단기금융상품":    30_000_000.0,
            "감가상각비":      20_000_000.0,
            "무형자산상각비":   5_000_000.0,
        }

    def test_net_margin_key_exists(self):
        ratios = calc_financial_ratios.invoke({"fs": self._make_fs_dict()})
        assert "net_margin" in ratios, "net_margin이 calc_financial_ratios 반환값에 없음"

    def test_net_margin_value_correct(self):
        fs = self._make_fs_dict()
        ratios = calc_financial_ratios.invoke({"fs": fs})
        expected = fs["당기순이익"] / fs["매출액"]
        assert ratios["net_margin"] == pytest.approx(expected)

    def test_net_margin_total_count(self):
        """비율/메타데이터 총 개수가 24개인지 확인한다."""
        ratios = calc_financial_ratios.invoke({"fs": self._make_fs_dict()})
        assert len(ratios) == 24, f"비율 개수 {len(ratios)}개 (기대: 24개)"


class TestEbitdaRatios:
    """EBITDA 계열 4개 지표 검증."""

    def _fs(self, **overrides) -> dict:
        base = {
            "매출액":         1_200_000_000.0,
            "매출원가":       800_000_000.0,
            "영업이익":       120_000_000.0,
            "당기순이익":     80_000_000.0,
            "이자비용":       30_000_000.0,
            "총자산":         2_000_000_000.0,
            "자본총계":       800_000_000.0,
            "부채총계":       1_200_000_000.0,
            "유동자산":       700_000_000.0,
            "유동부채":       400_000_000.0,
            "재고자산":       100_000_000.0,
            "매출채권":       120_000_000.0,
            "매입채무":       90_000_000.0,
            "단기차입금":     200_000_000.0,
            "유동성장기차입금": 50_000_000.0,
            "장기차입금":     300_000_000.0,
            "사채":           0.0,
            "영업현금흐름":   100_000_000.0,
            "유형자산취득":   40_000_000.0,
            "이익잉여금":     150_000_000.0,
            "유형자산":       500_000_000.0,
            "현금및현금성자산": 50_000_000.0,
            "단기금융상품":    30_000_000.0,
            "감가상각비":      20_000_000.0,
            "무형자산상각비":   5_000_000.0,
        }
        base.update(overrides)
        return base

    def _call(self, **overrides) -> dict:
        return calc_financial_ratios.invoke({"fs": self._fs(**overrides)})

    # ── 정상 케이스 ──────────────────────────────────────────────────────────

    def test_ebitda_value(self):
        """EBITDA = 영업이익 + 감가상각비 + 무형자산상각비."""
        ratios = self._call()
        expected = 120_000_000.0 + 20_000_000.0 + 5_000_000.0
        assert ratios["ebitda"] == pytest.approx(expected)

    def test_ebitda_margin_value(self):
        ratios = self._call()
        expected = (120_000_000.0 + 20_000_000.0 + 5_000_000.0) / 1_200_000_000.0
        assert ratios["ebitda_margin"] == pytest.approx(expected)

    def test_net_debt_to_ebitda_value(self):
        """순차입금 = 총차입금 - (현금 + 단기금융상품)."""
        ratios = self._call()
        total_borrow = 200_000_000.0 + 50_000_000.0 + 300_000_000.0 + 0.0
        net_debt     = total_borrow - (50_000_000.0 + 30_000_000.0)
        ebitda       = 120_000_000.0 + 20_000_000.0 + 5_000_000.0
        assert ratios["net_debt_to_ebitda"] == pytest.approx(net_debt / ebitda)

    def test_ebitda_to_interest_value(self):
        ratios = self._call()
        ebitda = 120_000_000.0 + 20_000_000.0 + 5_000_000.0
        assert ratios["ebitda_to_interest"] == pytest.approx(ebitda / 30_000_000.0)

    def test_zero_depreciation_ebitda_equals_op_income(self):
        """감가상각비·상각비 0 → EBITDA = 영업이익."""
        ratios = self._call(감가상각비=0.0, 무형자산상각비=0.0)
        assert ratios["ebitda"] == pytest.approx(120_000_000.0)

    # ── Edge case: EBITDA ≤ 0 ────────────────────────────────────────────────

    def test_negative_ebitda_ratios_are_none(self):
        """영업이익 음수, 감가상각 0 → EBITDA < 0 → 두 비율 None."""
        ratios = self._call(영업이익=-10_000_000.0, 감가상각비=0.0, 무형자산상각비=0.0)
        assert ratios["net_debt_to_ebitda"] is None
        assert ratios["ebitda_to_interest"] is None

    def test_zero_ebitda_ratios_are_none(self):
        """EBITDA = 0 → 두 비율 None."""
        ratios = self._call(영업이익=0.0, 감가상각비=0.0, 무형자산상각비=0.0)
        assert ratios["net_debt_to_ebitda"] is None
        assert ratios["ebitda_to_interest"] is None

    # ── Edge case: 이자비용 = 0 ───────────────────────────────────────────────

    def test_zero_interest_ebitda_to_interest_is_none(self):
        """이자비용 0 → ebitda_to_interest None (net_debt_to_ebitda는 정상)."""
        ratios = self._call(이자비용=0.0)
        assert ratios["ebitda_to_interest"] is None

    def test_low_quality_interest_expense_marks_estimated_ratio(self):
        ratios = self._call(
            이자비용=30_000_000.0,
            이자비용_원본계정="금융비용",
            이자비용_품질="low",
        )
        expected_ebitda = 120_000_000.0 + 20_000_000.0 + 5_000_000.0
        assert ratios["interest_coverage"] == pytest.approx(120_000_000.0 / 30_000_000.0)
        assert ratios["ebitda_to_interest"] == pytest.approx(expected_ebitda / 30_000_000.0)
        assert ratios["interest_ratio_estimated"] is False
        assert "금융비용" in str(ratios["interest_ratio_note"])

    def test_negative_low_quality_interest_expense_excludes_ratio(self):
        ratios = self._call(
            영업이익=5_000_000_000.0,
            이자비용=-10_000_000.0,
            이자비용_원본계정="금융원가",
            이자비용_품질="low",
        )
        assert ratios["interest_coverage"] is None
        assert ratios["ebitda_to_interest"] is None
        assert "산출에서 제외" in str(ratios["interest_ratio_note"])
        assert ratios["net_debt_to_ebitda"] is not None

    # ── DB 경로 폴백: 새 키 없는 fs ───────────────────────────────────────────

    def test_missing_new_keys_no_crash(self):
        """감가상각비·현금 등 4개 키가 없어도 KeyError 없이 계산."""
        fs_without_new_keys = {k: v for k, v in self._fs().items()
                               if k not in ("감가상각비", "무형자산상각비",
                                            "현금및현금성자산", "단기금융상품")}
        ratios = calc_financial_ratios.invoke({"fs": fs_without_new_keys})
        # 키 없으면 0.0 폴백 → EBITDA = 영업이익, net_debt = 총차입금
        assert ratios["ebitda"] == pytest.approx(120_000_000.0)
        assert ratios["net_debt_to_ebitda"] is not None
