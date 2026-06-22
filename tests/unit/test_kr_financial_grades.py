"""KR 재무지표 등급 매핑 테스트

calc_kr_financial_grades 가 JSON 캐시를 읽어 올바른 등급을 반환하는지 검증.
"""

from __future__ import annotations

import pytest

from backend.tools.kr_grade_mapper import calc_kr_financial_grades


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────

def _make_ratios(**overrides) -> dict:
    """calc_financial_ratios 반환 형태와 동일한 dict. 기본값은 A 근처."""
    base = {
        # percent 계열 (소수값): ebitda_margin 9% → 0.09
        "ebitda_margin":      0.09,    # 9% → A (≥8%)
        # times 계열
        "net_debt_to_ebitda": 3.0,     # 3.0배 → A (≤3.5)
        "ebitda_to_interest": 5.0,     # 5.0배 → A (≥4.5)
        # percent 계열 (소수값): debt_ratio 130% → 0.13 로 저장(×100 = 130)
        # 주의: calc_financial_ratios의 debt_ratio = 부채총계/자본총계 (소수)
        "debt_ratio":         1.30,    # 130% → A (≤150%)
        "borrow_dep":         0.32,    # 32%  → A (≤35%)
    }
    base.update(overrides)
    return base


# ── 1. corporate_제조 정상 케이스 ────────────────────────────────────────────

class TestCorporateSeoul:
    def _call(self, **overrides) -> dict:
        return calc_kr_financial_grades(_make_ratios(**overrides), "corporate_제조")

    def test_returns_dict_with_required_keys(self):
        result = self._call()
        assert result is not None
        assert result["methodology"] == "corporate_제조"
        assert "per_metric_grades" in result
        assert "scope_note" in result

    def test_five_metrics_present(self):
        result = self._call()
        keys = set(result["per_metric_grades"])
        assert keys == {"ebitda_margin", "net_debt_to_ebitda", "ebitda_to_interest",
                        "debt_ratio", "borrow_dep"}

    def test_grade_A_baseline(self):
        result = self._call()
        grades = {k: v["grade"] for k, v in result["per_metric_grades"].items()}
        assert grades["ebitda_margin"]      == "A"
        assert grades["net_debt_to_ebitda"] == "A"
        assert grades["ebitda_to_interest"] == "A"
        assert grades["debt_ratio"]         == "A"
        assert grades["borrow_dep"]         == "A"

    def test_weight_strings(self):
        result = self._call()
        pg = result["per_metric_grades"]
        assert pg["ebitda_margin"]["weight"]      == "5%"
        assert pg["net_debt_to_ebitda"]["weight"] == "15%"
        assert pg["ebitda_to_interest"]["weight"] == "5%"
        assert pg["debt_ratio"]["weight"]         == "5%"
        assert pg["borrow_dep"]["weight"]         == "10%"

    def test_value_is_percent_for_percent_metrics(self):
        """percent 단위 지표는 value가 ×100 변환된 값으로 저장돼야 한다."""
        result = self._call()
        pg = result["per_metric_grades"]
        assert abs(pg["ebitda_margin"]["value"] - 9.0)   < 0.01   # 0.09 × 100
        assert abs(pg["debt_ratio"]["value"]    - 130.0) < 0.01   # 1.30 × 100
        assert abs(pg["borrow_dep"]["value"]    - 32.0)  < 0.01   # 0.32 × 100

    # ── 등급 경계값 ──

    @pytest.mark.parametrize("ebitda_margin_pct, expected_grade", [
        (0.21,  "AAA"),   # 21% ≥ 20%
        (0.20,  "AAA"),   # 경계: 20% = 20% → AAA (gte)
        (0.1999, "AA"),   # 19.99% → AA
        (0.12,  "AA"),    # 12% → AA
        (0.08,  "A"),
        (0.06,  "BBB"),
        (0.04,  "BB"),
        (0.039, "B"),     # 3.9% < 4%
    ])
    def test_ebitda_margin_boundaries(self, ebitda_margin_pct, expected_grade):
        result = self._call(ebitda_margin=ebitda_margin_pct)
        assert result["per_metric_grades"]["ebitda_margin"]["grade"] == expected_grade

    @pytest.mark.parametrize("net_debt_to_ebitda, expected_grade", [
        (0.5,  "AAA"),
        (0.51, "AA"),
        (1.5,  "AA"),
        (1.51, "A"),
        (3.5,  "A"),
        (3.51, "BBB"),
        (7.0,  "BBB"),
        (7.01, "BB"),
        (10.0, "BB"),
        (10.01, "B"),
    ])
    def test_net_debt_to_ebitda_boundaries(self, net_debt_to_ebitda, expected_grade):
        result = self._call(net_debt_to_ebitda=net_debt_to_ebitda)
        assert result["per_metric_grades"]["net_debt_to_ebitda"]["grade"] == expected_grade

    @pytest.mark.parametrize("debt_ratio_decimal, expected_grade", [
        (0.50,  "AAA"),   # 50% → AAA
        (0.501, "AA"),
        (1.00,  "AA"),    # 100%
        (1.001, "A"),
        (1.50,  "A"),
        (1.501, "BBB"),
        (2.00,  "BBB"),
        (2.001, "BB"),
        (3.00,  "BB"),
        (3.001, "B"),
    ])
    def test_debt_ratio_boundaries(self, debt_ratio_decimal, expected_grade):
        result = self._call(debt_ratio=debt_ratio_decimal)
        assert result["per_metric_grades"]["debt_ratio"]["grade"] == expected_grade


# ── 2. 제약업 — 가중치만 다르고 임계값 동일 ────────────────────────────────

class TestPharma:
    def _call(self, **overrides) -> dict:
        return calc_kr_financial_grades(_make_ratios(**overrides), "제약업")

    def test_methodology_name(self):
        result = self._call()
        assert result["methodology"] == "제약업"

    def test_pharma_weights_differ_from_corporate(self):
        result = self._call()
        pg = result["per_metric_grades"]
        assert pg["ebitda_margin"]["weight"]      == "7.5%"
        assert pg["net_debt_to_ebitda"]["weight"] == "15%"
        assert pg["ebitda_to_interest"]["weight"] == "7.5%"
        assert pg["debt_ratio"]["weight"]         == "10%"
        assert pg["borrow_dep"]["weight"]         == "10%"

    def test_pharma_thresholds_same_as_corporate(self):
        """임계값이 같으므로 동일한 입력에서 등급도 같아야 한다."""
        corp   = calc_kr_financial_grades(_make_ratios(), "corporate_제조")
        pharma = calc_kr_financial_grades(_make_ratios(), "제약업")
        for k in corp["per_metric_grades"]:
            assert corp["per_metric_grades"][k]["grade"] == pharma["per_metric_grades"][k]["grade"]


# ── 3. Edge case: None 값 ─────────────────────────────────────────────────────

class TestNoneValues:
    def test_none_ebitda_to_interest_yields_none_grade(self):
        ratios = _make_ratios(ebitda_to_interest=None)
        result = calc_kr_financial_grades(ratios, "corporate_제조")
        ei = result["per_metric_grades"]["ebitda_to_interest"]
        assert ei["grade"] is None
        assert ei["value"] is None
        assert ei["note"]  == "산출불가"

    def test_none_net_debt_to_ebitda_yields_none_grade(self):
        ratios = _make_ratios(net_debt_to_ebitda=None)
        result = calc_kr_financial_grades(ratios, "제약업")
        nd = result["per_metric_grades"]["net_debt_to_ebitda"]
        assert nd["grade"] is None

    def test_other_metrics_unaffected_when_one_is_none(self):
        ratios = _make_ratios(ebitda_to_interest=None)
        result = calc_kr_financial_grades(ratios, "corporate_제조")
        pg = result["per_metric_grades"]
        assert pg["ebitda_margin"]["grade"]      is not None
        assert pg["net_debt_to_ebitda"]["grade"] is not None
        assert pg["debt_ratio"]["grade"]         is not None
        assert pg["borrow_dep"]["grade"]         is not None


# ── 4. 지원하지 않는 sub_sector ──────────────────────────────────────────────

def test_unsupported_sub_sector_returns_none():
    result = calc_kr_financial_grades(_make_ratios(), "건설")
    assert result is None

def test_empty_sub_sector_returns_none():
    result = calc_kr_financial_grades(_make_ratios(), "")
    assert result is None
