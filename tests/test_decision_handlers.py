"""Decision Agent 핸들러 단위 테스트 (고도화 포함)

실행: python -m pytest tests/test_decision_handlers.py -v
"""

from __future__ import annotations

import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agents.decision.models import (
    CreditGrade, DecisionResult,
)
from backend.agents.decision.handlers.grade_calculator import calculate_grade
from backend.agents.decision.handlers.decision_maker import make_decision
from backend.agents.decision.handlers.limit_recommender import recommend_limit


# ════════════════════════════════════════════════════════════════════════════
# 픽스처
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def clean_context():
    return {
        "company_name": "우량기업",
        "corp_code": "00000001",
        "critical_count": 0, "high_count": 0,
        "medium_count": 0,   "low_count": 0,
        "overall_risk_level": "low",
        "latest_debt_ratio": 80.0,
        "latest_op_margin": 12.0,
        "is_net_income_negative": False,
        "total_assets": 50_000_000_000,
        "revenue": 30_000_000_000,
        "classified_events": [],
    }

@pytest.fixture
def critical_context():
    return {
        "company_name": "위기기업",
        "corp_code": "00000002",
        "critical_count": 2, "high_count": 1,
        "medium_count": 3,   "low_count": 2,
        "overall_risk_level": "critical",
        "latest_debt_ratio": 350.0,
        "latest_op_margin": -15.0,
        "is_net_income_negative": True,
        "total_assets": 20_000_000_000,
        "revenue": 10_000_000_000,
        "classified_events": [],
    }

@pytest.fixture
def capital_impaired_context():
    """자본잠식 컨텍스트"""
    from backend.agents.risk_event.models import (
        RiskEvent, EventType, EventSource, SeverityClassifiedEvent, SeverityLevel,
    )
    from datetime import date
    ev = RiskEvent(
        event_type=EventType.FINANCIAL_ANOMALY,
        source=EventSource.FINANCIAL_DATA,
        title="자본잠식 (2024)",
        description="자본총계 음수",
        detected_at=date.today(),
    )
    sce = SeverityClassifiedEvent(
        event=ev, severity=SeverityLevel.CRITICAL, score=90, rationale=""
    )
    return {
        "company_name": "잠식기업",
        "corp_code": "00000003",
        "critical_count": 1, "high_count": 0,
        "medium_count": 0,   "low_count": 0,
        "overall_risk_level": "critical",
        "latest_debt_ratio": None,
        "latest_op_margin": None,
        "is_net_income_negative": True,
        "classified_events": [sce],
    }

@pytest.fixture
def many_high_context():
    """HIGH 이벤트 5건 이상"""
    return {
        "company_name": "다중위험기업",
        "corp_code": "00000004",
        "critical_count": 0, "high_count": 6,
        "medium_count": 2,   "low_count": 1,
        "overall_risk_level": "high",
        "latest_debt_ratio": 180.0,
        "latest_op_margin": 2.0,
        "is_net_income_negative": False,
        "classified_events": [],
    }

@pytest.fixture
def double_financial_risk_context():
    """당기순손실 + 부채비율 300% 초과"""
    return {
        "company_name": "재무위험기업",
        "corp_code": "00000005",
        "critical_count": 0, "high_count": 1,
        "medium_count": 2,   "low_count": 0,
        "overall_risk_level": "high",
        "latest_debt_ratio": 320.0,
        "latest_op_margin": -5.0,
        "is_net_income_negative": True,
        "classified_events": [],
    }


# ════════════════════════════════════════════════════════════════════════════
# D-001 | 신용등급 산출
# ════════════════════════════════════════════════════════════════════════════

class TestGradeCalculator:

    def test_clean_company_gets_high_grade(self, clean_context):
        result = calculate_grade(clean_context)
        assert result.grade in (CreditGrade.A, CreditGrade.B)
        assert result.score >= 65

    def test_critical_events_lower_grade(self, critical_context):
        result = calculate_grade(critical_context)
        assert result.grade in (CreditGrade.D, CreditGrade.E)
        assert result.score < 50

    def test_capital_impaired_forces_grade_e(self, capital_impaired_context):
        result = calculate_grade(capital_impaired_context)
        assert result.grade == CreditGrade.E
        assert result.score == 0

    def test_score_in_range(self, clean_context):
        result = calculate_grade(clean_context)
        assert 0 <= result.score <= 100

    def test_score_breakdown_consistent(self, clean_context):
        result = calculate_grade(clean_context)
        bd = result.score_breakdown
        assert bd.final_score == result.score

    def test_grade_cap_applied(self, clean_context):
        clean_context["grade_cap"] = "BB+"
        result = calculate_grade(clean_context)
        assert result.grade in (CreditGrade.C, CreditGrade.D, CreditGrade.E)

    def test_high_debt_ratio_deducts_points(self, clean_context):
        base = calculate_grade(clean_context).score
        clean_context["latest_debt_ratio"] = 450.0
        risky = calculate_grade(clean_context).score
        assert risky < base

    def test_many_high_events_extra_deduction(self, many_high_context):
        result = calculate_grade(many_high_context)
        # HIGH 6건 → 기본 차감 30점 + 추가 10점
        assert result.score_breakdown.risk_deduction >= 40

    def test_rationale_not_empty(self, clean_context):
        result = calculate_grade(clean_context)
        assert len(result.rationale) > 0

    # 등급 경계값 테스트
    @pytest.mark.parametrize("score_override,expected_grade", [
        (100, CreditGrade.A),
        (80,  CreditGrade.A),
        (79,  CreditGrade.B),
        (65,  CreditGrade.B),
        (64,  CreditGrade.C),
        (50,  CreditGrade.C),
        (49,  CreditGrade.D),
        (35,  CreditGrade.D),
        (34,  CreditGrade.E),
        (0,   CreditGrade.E),
    ])
    def test_grade_boundaries(self, score_override, expected_grade):
        """점수-등급 경계값 테이블 검증"""
        from backend.agents.decision.handlers.grade_calculator import _score_to_grade
        assert _score_to_grade(score_override) == expected_grade


# ════════════════════════════════════════════════════════════════════════════
# D-002 | 승인·거절 판단
# ════════════════════════════════════════════════════════════════════════════

class TestDecisionMaker:

    def test_grade_a_approves(self, clean_context):
        result = make_decision(CreditGrade.A, 90, clean_context)
        assert result.result == DecisionResult.APPROVE

    def test_grade_b_approves(self, clean_context):
        result = make_decision(CreditGrade.B, 70, clean_context)
        assert result.result == DecisionResult.APPROVE

    def test_grade_c_reviews(self, clean_context):
        result = make_decision(CreditGrade.C, 55, clean_context)
        assert result.result == DecisionResult.REVIEW

    def test_grade_d_rejects(self, clean_context):
        result = make_decision(CreditGrade.D, 40, clean_context)
        assert result.result == DecisionResult.REJECT

    def test_grade_e_rejects(self, clean_context):
        result = make_decision(CreditGrade.E, 10, clean_context)
        assert result.result == DecisionResult.REJECT

    def test_critical_event_overrides_to_reject(self, critical_context):
        result = make_decision(CreditGrade.B, 70, critical_context)
        assert result.result == DecisionResult.REJECT
        assert result.confidence >= 0.90

    def test_many_high_events_overrides_to_reject(self, many_high_context):
        result = make_decision(CreditGrade.B, 68, many_high_context)
        assert result.result == DecisionResult.REJECT

    def test_double_financial_risk_overrides_to_reject(self, double_financial_risk_context):
        result = make_decision(CreditGrade.C, 52, double_financial_risk_context)
        assert result.result == DecisionResult.REJECT

    def test_confidence_range(self, clean_context):
        result = make_decision(CreditGrade.A, 90, clean_context)
        assert 0.0 <= result.confidence <= 1.0

    def test_reasons_not_empty(self, clean_context):
        result = make_decision(CreditGrade.A, 90, clean_context)
        assert len(result.reasons) >= 1

    def test_override_reason_prepended(self, critical_context):
        result = make_decision(CreditGrade.B, 70, critical_context)
        assert "CRITICAL" in result.reasons[0] or "자동 거절" in result.reasons[0]

    @pytest.mark.parametrize("score,expected_approve_conf_range", [
        (90, (0.8, 1.0)),
        (80, (0.7, 1.0)),
        (65, (0.6, 0.9)),
    ])
    def test_approve_confidence_increases_with_score(self, clean_context, score, expected_approve_conf_range):
        result = make_decision(CreditGrade.A, score, clean_context)
        lo, hi = expected_approve_conf_range
        assert lo <= result.confidence <= hi, f"score={score} confidence={result.confidence}"


# ════════════════════════════════════════════════════════════════════════════
# D-003 | 한도 추천
# ════════════════════════════════════════════════════════════════════════════

class TestLimitRecommender:

    def test_rejected_returns_zero(self, clean_context):
        result = recommend_limit(CreditGrade.A, DecisionResult.REJECT, clean_context)
        assert result.recommended_limit == 0

    def test_grade_a_has_limit(self, clean_context):
        result = recommend_limit(CreditGrade.A, DecisionResult.APPROVE, clean_context)
        assert result.recommended_limit and result.recommended_limit > 0

    def test_grade_b_limit_less_than_a(self, clean_context):
        ctx_a = {**clean_context, "total_assets": 50_000_000_000, "revenue": 30_000_000_000}
        ctx_b = {**clean_context, "total_assets": 50_000_000_000, "revenue": 30_000_000_000}
        a = recommend_limit(CreditGrade.A, DecisionResult.APPROVE, ctx_a).recommended_limit
        b = recommend_limit(CreditGrade.B, DecisionResult.APPROVE, ctx_b).recommended_limit
        assert a >= b

    def test_grade_c_conditional(self, clean_context):
        result = recommend_limit(CreditGrade.C, DecisionResult.REVIEW, clean_context)
        assert result.recommended_limit is not None

    def test_grade_d_no_limit(self, clean_context):
        result = recommend_limit(CreditGrade.D, DecisionResult.REJECT, clean_context)
        assert result.recommended_limit == 0

    def test_limit_cap_respected(self, clean_context):
        """총자산 기반 한도가 등급별 상한을 초과하지 않아야 함"""
        huge_ctx = {**clean_context,
                    "total_assets": 1_000_000_000_000,
                    "revenue": 500_000_000_000}
        result = recommend_limit(CreditGrade.A, DecisionResult.APPROVE, huge_ctx)
        assert result.recommended_limit <= 5_000_000_000   # A등급 상한 50억

    def test_fallback_when_no_financial_data(self):
        ctx = {"company_name": "테스트", "corp_code": "00000001"}
        result = recommend_limit(CreditGrade.B, DecisionResult.APPROVE, ctx)
        assert result.recommended_limit is not None
        assert result.recommended_limit > 0

    def test_limit_range_format(self, clean_context):
        result = recommend_limit(CreditGrade.A, DecisionResult.APPROVE, clean_context)
        assert result.limit_range is not None
        assert "~" in result.limit_range

    def test_limit_basis_not_empty(self, clean_context):
        result = recommend_limit(CreditGrade.A, DecisionResult.APPROVE, clean_context)
        assert len(result.limit_basis) > 0
