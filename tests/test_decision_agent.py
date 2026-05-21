"""Decision Agent 테스트

실행 방법:
    pytest tests/test_decision_agent.py -v

외부 API(Claude) 의존 테스트는 mock으로 고립 실행한다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from agents.decision.handlers.grade_calculator import calculate_grade
from agents.decision.handlers.decision_maker import make_decision
from agents.decision.handlers.limit_recommender import recommend_limit
from agents.decision.models import CreditGrade, DecisionResult


# ─── 공통 픽스처 ─────────────────────────────────────────────────────────────

@pytest.fixture
def clean_context():
    """리스크 이벤트 없는 정상 기업 컨텍스트."""
    return {
        "company_name":          "정상기업",
        "corp_code":             "00123456",
        "critical_count":        0,
        "high_count":            0,
        "medium_count":          0,
        "low_count":             0,
        "latest_debt_ratio":     80.0,
        "latest_op_margin":      12.5,
        "is_net_income_negative": False,
        "total_assets":          10_000_000_000,   # 100억
        "revenue":                5_000_000_000,   #  50억
    }


@pytest.fixture
def risky_context():
    """리스크 이벤트 다수 + 재무 이상 기업 컨텍스트."""
    return {
        "company_name":           "위험기업",
        "corp_code":              "00654321",
        "critical_count":         2,
        "high_count":             3,
        "medium_count":           5,
        "low_count":              2,
        "latest_debt_ratio":      350.0,
        "latest_op_margin":       -5.0,
        "is_net_income_negative": True,
        "total_assets":           3_000_000_000,
        "revenue":                1_000_000_000,
    }


@pytest.fixture
def no_financial_context():
    """재무 데이터 없는 컨텍스트 (CSV 미존재 등)."""
    return {
        "company_name":  "데이터없는기업",
        "corp_code":     "00000001",
        "critical_count": 0,
        "high_count":     1,
        "medium_count":   2,
        "low_count":      0,
    }


# ─── D-001 신용등급 산출 테스트 ───────────────────────────────────────────────

class TestGradeCalculator:
    def test_clean_company_gets_high_grade(self, clean_context):
        result = calculate_grade(clean_context)
        assert result.grade in (CreditGrade.A, CreditGrade.B)
        assert result.score >= 65

    def test_risky_company_gets_low_grade(self, risky_context):
        result = calculate_grade(risky_context)
        assert result.grade in (CreditGrade.D, CreditGrade.E)
        assert result.score < 50

    def test_score_is_within_range(self, clean_context):
        result = calculate_grade(clean_context)
        assert 0 <= result.score <= 100

    def test_grade_cap_applied(self, clean_context):
        """financial_analyst grade_cap이 더 엄격할 때 적용되어야 한다."""
        clean_context["grade_cap"] = "CCC"
        result = calculate_grade(clean_context)
        assert result.grade == CreditGrade.E

    def test_no_financial_data_does_not_crash(self, no_financial_context):
        result = calculate_grade(no_financial_context)
        assert result.grade is not None
        assert result.score >= 0

    def test_score_breakdown_sums_correctly(self, risky_context):
        result = calculate_grade(risky_context)
        b = result.score_breakdown
        expected = b.base_score - b.risk_deduction - b.financial_deduction
        assert result.score == max(0, expected)


# ─── D-002 승인·거절 판단 테스트 ─────────────────────────────────────────────

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

    def test_grade_d_rejects(self, risky_context):
        result = make_decision(CreditGrade.D, 40, risky_context)
        assert result.result == DecisionResult.REJECT

    def test_grade_e_rejects(self, risky_context):
        result = make_decision(CreditGrade.E, 20, risky_context)
        assert result.result == DecisionResult.REJECT

    def test_critical_event_forces_reject(self, clean_context):
        """CRITICAL 이벤트가 있으면 등급 무관하게 거절."""
        clean_context["critical_count"] = 1
        result = make_decision(CreditGrade.A, 85, clean_context)
        assert result.result == DecisionResult.REJECT

    def test_confidence_is_between_0_and_1(self, clean_context):
        result = make_decision(CreditGrade.B, 72, clean_context)
        assert 0.0 <= result.confidence <= 1.0

    def test_reasons_are_not_empty(self, clean_context):
        result = make_decision(CreditGrade.A, 88, clean_context)
        assert len(result.reasons) > 0


# ─── D-003 한도 추천 테스트 ───────────────────────────────────────────────────

class TestLimitRecommender:
    def test_approve_has_positive_limit(self, clean_context):
        result = recommend_limit(CreditGrade.A, DecisionResult.APPROVE, clean_context)
        assert result.recommended_limit is not None
        assert result.recommended_limit > 0

    def test_reject_has_zero_limit(self, risky_context):
        result = recommend_limit(CreditGrade.E, DecisionResult.REJECT, risky_context)
        assert result.recommended_limit == 0

    def test_grade_a_limit_higher_than_grade_b(self, clean_context):
        limit_a = recommend_limit(CreditGrade.A, DecisionResult.APPROVE, clean_context)
        limit_b = recommend_limit(CreditGrade.B, DecisionResult.APPROVE, clean_context)
        assert limit_a.recommended_limit >= limit_b.recommended_limit

    def test_limit_does_not_exceed_cap(self, clean_context):
        """A등급 한도 상한 50억 초과하지 않아야 한다."""
        clean_context["total_assets"] = 1_000_000_000_000  # 1조
        clean_context["revenue"]      = 1_000_000_000_000
        result = recommend_limit(CreditGrade.A, DecisionResult.APPROVE, clean_context)
        assert result.recommended_limit <= 5_000_000_000  # 50억

    def test_no_financial_data_uses_default(self, no_financial_context):
        result = recommend_limit(CreditGrade.B, DecisionResult.APPROVE, no_financial_context)
        assert result.recommended_limit is not None
        assert "기본값" in result.limit_basis

    def test_limit_range_is_set_when_approved(self, clean_context):
        result = recommend_limit(CreditGrade.B, DecisionResult.APPROVE, clean_context)
        assert result.limit_range is not None


# ─── 전체 워크플로우 통합 테스트 ─────────────────────────────────────────────

class TestDecisionAgentWorkflow:
    def test_full_workflow_clean_company(self, clean_context):
        """정상 기업 전체 흐름 — Claude API mock 처리."""
        mock_explanation = {
            "summary":              "리스크 낮은 우량 기업입니다.",
            "key_risk_factors":     [],
            "key_positive_factors": ["부채비율 양호", "영업이익률 양호"],
            "recommendation":       "승인을 권고합니다.",
        }
        with patch(
            "agents.decision.handlers.explanation_generator.call_claude",
            new_callable=AsyncMock,
            return_value=str(mock_explanation),
        ), patch(
            "agents.decision.handlers.explanation_generator.parse_json_response",
            return_value=mock_explanation,
        ), patch(
            "agents.decision.handlers.explanation_generator.get_client",
        ) as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_client.return_value.__aexit__  = AsyncMock(return_value=False)

            from agents.decision.agent import DecisionAgent
            agent = DecisionAgent()
            result = asyncio.run(agent.run(clean_context))

        assert result.get("decision") in ("approve", "review", "reject")
        assert result.get("credit_grade") in ("A", "B", "C", "D", "E")
        assert isinstance(result.get("credit_score"), int)

    def test_full_workflow_risky_company(self, risky_context):
        """위험 기업 전체 흐름 — 거절 결정 예상."""
        mock_explanation = {
            "summary":              "다수의 리스크 이벤트가 탐지되었습니다.",
            "key_risk_factors":     ["CRITICAL 이벤트 2건", "부채비율 350%"],
            "key_positive_factors": [],
            "recommendation":       "거절을 권고합니다.",
        }
        with patch(
            "agents.decision.handlers.explanation_generator.call_claude",
            new_callable=AsyncMock,
            return_value=str(mock_explanation),
        ), patch(
            "agents.decision.handlers.explanation_generator.parse_json_response",
            return_value=mock_explanation,
        ), patch(
            "agents.decision.handlers.explanation_generator.get_client",
        ) as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_client.return_value.__aexit__  = AsyncMock(return_value=False)

            from agents.decision.agent import DecisionAgent
            agent = DecisionAgent()
            result = asyncio.run(agent.run(risky_context))

        assert result.get("decision") == "reject"

    def test_agent_returns_dict(self, clean_context):
        """run()이 반드시 dict를 반환해야 한다 (Agent 프로토콜)."""
        with patch(
            "agents.decision.handlers.explanation_generator.call_claude",
            new_callable=AsyncMock,
            return_value="{}",
        ), patch(
            "agents.decision.handlers.explanation_generator.parse_json_response",
            return_value={},
        ), patch(
            "agents.decision.handlers.explanation_generator.get_client",
        ) as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_client.return_value.__aexit__  = AsyncMock(return_value=False)

            from agents.decision.agent import DecisionAgent
            agent  = DecisionAgent()
            result = asyncio.run(agent.run(clean_context))

        assert isinstance(result, dict)
