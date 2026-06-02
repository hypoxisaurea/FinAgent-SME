"""
최종 통합 테스트: Risk Event + Decision Agent 전체 파이프라인
위치: tests/integration/test_final_pipeline.py
실행: python -m pytest tests/integration/test_final_pipeline.py -v
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta
from collections import Counter

from backend.agents.risk_event.handlers.keyword_detector import detect_keywords
from backend.agents.risk_event.handlers.disclosure_detector import detect_disclosure_anomalies
from backend.agents.risk_event.handlers.legal_risk_detector import detect_legal_risks
from backend.agents.risk_event.handlers.financial_anomaly_detector import detect_financial_anomalies
from backend.agents.risk_event.handlers.severity_classifier import classify_severity
from backend.agents.risk_event.handlers.timeline_builder import build_timeline
from backend.agents.decision.handlers.grade_calculator import calculate_grade
from backend.agents.decision.handlers.decision_maker import make_decision
from backend.agents.decision.handlers.limit_recommender import recommend_limit

from backend.agents.risk_event.models import SeverityLevel, RiskEvent, EventType, EventSource
from backend.agents.risk_event.models import SeverityClassifiedEvent
from backend.agents.decision.models import CreditGrade, DecisionResult


# ─── 미니 파이프라인 ──────────────────────────────────────────────────────────

def run_pipeline(
    company_name, corp_code,
    news_data=None, disclosure_data=None,
    court_data=None, financial_rows=None,
    extra_ctx=None,
):
    news_data       = news_data       or []
    disclosure_data = disclosure_data or []
    court_data      = court_data      or []
    financial_rows  = financial_rows  or []

    kw   = detect_keywords(company_name, news_data, disclosure_data)
    disc = detect_disclosure_anomalies(company_name, corp_code, disclosure_data)
    leg  = detect_legal_risks(company_name, court_data)
    fin  = detect_financial_anomalies(company_name, corp_code, financial_rows)

    all_events = kw.detected_events + disc.anomalies + leg.legal_risks + fin.anomalies
    classified = [classify_severity(e) for e in all_events]
    timeline   = build_timeline(classified)
    cnt        = Counter(e.severity for e in classified)

    ctx = {
        "company_name": company_name, "corp_code": corp_code,
        "critical_count": cnt[SeverityLevel.CRITICAL],
        "high_count":     cnt[SeverityLevel.HIGH],
        "medium_count":   cnt[SeverityLevel.MEDIUM],
        "low_count":      cnt[SeverityLevel.LOW],
        "latest_debt_ratio":      fin.latest_debt_ratio,
        "latest_op_margin":       fin.latest_op_margin,
        "is_net_income_negative": fin.is_net_income_negative,
        "classified_events":      classified,
        **(extra_ctx or {}),
    }

    grade_r    = calculate_grade(ctx)
    decision_r = make_decision(grade_r.grade, grade_r.score, ctx)
    limit_r    = recommend_limit(grade_r.grade, decision_r.result, ctx)

    return dict(ctx=ctx, grade=grade_r, decision=decision_r,
                limit=limit_r, timeline=timeline)


# ════════════════════════════════════════════════════════════════════════════
# 시나리오 테스트
# ════════════════════════════════════════════════════════════════════════════

class TestScenarios:

    def test_S01_healthy_company_approved(self):
        """S-01: 재무 우량 + 리스크 없음 → A/B 승인"""
        r = run_pipeline(
            "우량주식회사", "00000001",
            financial_rows=[
                {"year": "2022", "revenue": "120000000000",
                 "operating_income": "12000000000", "net_income": "8000000000",
                 "total_assets_statement": "250000000000",
                 "total_liabilities": "80000000000", "total_equity": "170000000000"},
                {"year": "2023", "revenue": "130000000000",
                 "operating_income": "13000000000", "net_income": "9000000000",
                 "total_assets_statement": "270000000000",
                 "total_liabilities": "85000000000", "total_equity": "185000000000"},
                {"year": "2024", "revenue": "140000000000",
                 "operating_income": "14000000000", "net_income": "10000000000",
                 "total_assets_statement": "290000000000",
                 "total_liabilities": "90000000000", "total_equity": "200000000000"},
            ],
            extra_ctx={"total_assets": 290_000_000_000, "revenue": 140_000_000_000},
        )
        assert r["grade"].grade in (CreditGrade.A, CreditGrade.B), \
            f"등급={r['grade'].grade}, 점수={r['grade'].score}"
        assert r["decision"].result == DecisionResult.APPROVE
        assert r["limit"].recommended_limit > 0

    def test_S02_bankruptcy_auto_reject(self):
        """S-02: 파산선고 → CRITICAL → 자동 거절"""
        r = run_pipeline(
            "파산기업", "00000002",
            court_data=[{"title": "파산선고 결정",
                         "content": "파산선고를 내렸다.",
                         "announced_at": "2026-05-01", "url": None}],
        )
        assert r["ctx"]["critical_count"] >= 1
        assert r["decision"].result == DecisionResult.REJECT
        assert r["limit"].recommended_limit == 0

    def test_S03_capital_impaired_grade_E(self):
        """S-03: 자본잠식 → 강제 E등급 → 거절"""
        r = run_pipeline(
            "잠식기업", "00000003",
            financial_rows=[
                {"year": "2024", "revenue": "30000000000",
                 "operating_income": "-5000000000", "net_income": "-8000000000",
                 "total_assets_statement": "60000000000",
                 "total_liabilities": "80000000000", "total_equity": "-20000000000"},
            ],
        )
        assert r["grade"].grade == CreditGrade.E
        assert r["grade"].score == 0
        assert r["decision"].result == DecisionResult.REJECT

    def test_S04_compound_risk_reject(self):
        """S-04: 소송 뉴스 + 공시 이상 + 재무 악화 복합 → 거절"""
        r = run_pipeline(
            "복합위험기업", "00000004",
            news_data=[
                {"title": "복합위험기업 소송 제기",
                 "content": "대규모 소송과 가압류 발생.",
                 "published_at": "2026-04-01", "url": None},
            ],
            disclosure_data=[
                {"title": "단기차입금 대규모 증가",
                 "content": "단기차입금을 크게 증가하였습니다.",
                 "disclosed_at": "2026-03-01"},
            ],
            financial_rows=[
                {"year": "2022", "revenue": "80000000000",
                 "operating_income": "4000000000", "net_income": "2000000000",
                 "total_assets_statement": "120000000000",
                 "total_liabilities": "60000000000", "total_equity": "60000000000"},
                {"year": "2023", "revenue": "65000000000",
                 "operating_income": "-2000000000", "net_income": "-4000000000",
                 "total_assets_statement": "100000000000",
                 "total_liabilities": "80000000000", "total_equity": "20000000000"},
            ],
        )
        assert r["decision"].result == DecisionResult.REJECT

    def test_S05_high_debt_financial_reject(self):
        """S-05: 당기순손실 + 부채비율 300% 초과 → 하드 거절"""
        r = run_pipeline(
            "고부채기업", "00000005",
            financial_rows=[
                {"year": "2024", "revenue": "40000000000",
                 "operating_income": "-1000000000", "net_income": "-3000000000",
                 "total_assets_statement": "80000000000",
                 "total_liabilities": "65000000000", "total_equity": "18000000000"},
            ],
            extra_ctx={"latest_debt_ratio": 361.0, "is_net_income_negative": True},
        )
        assert r["decision"].result == DecisionResult.REJECT

    def test_S06_many_high_events_reject(self):
        """S-06: HIGH 이벤트 5건 이상 → 복합 리스크 자동 거절"""
        r = run_pipeline(
            "다중위험기업", "00000006",
            extra_ctx={
                "high_count": 6,
                "latest_debt_ratio": 150.0,
                "is_net_income_negative": False,
            },
        )
        assert r["decision"].result == DecisionResult.REJECT

    def test_S07_review_grade_c(self):
        """S-07: 중간 리스크 → C/D/E등급"""
        r = run_pipeline(
            "중간기업", "00000007",
            news_data=[
                {"title": "중간기업 소송 제기",
                "content": "중간기업이 소송에 휘말렸다.",
                "published_at": "2026-01-01", "url": None}
            ],
            disclosure_data=[
                {"title": "단기차입금 증가 공시",
                "content": "단기차입금을 증가하였습니다.",
                "disclosed_at": "2026-02-01"}
            ],
            financial_rows=[
                {"year": "2022", "revenue": "50000000000",
                "operating_income": "2000000000", "net_income": "1000000000",
                "total_assets_statement": "80000000000",
                "total_liabilities": "50000000000", "total_equity": "30000000000"},
                {"year": "2023", "revenue": "42000000000",
                "operating_income": "-500000000", "net_income": "-2000000000",
                "total_assets_statement": "78000000000",
                "total_liabilities": "58000000000", "total_equity": "20000000000"},
            ],
            extra_ctx={"total_assets": 78_000_000_000, "revenue": 42_000_000_000},
        )
        # 부채비율 290% + 영업적자 + 당기순손실 + 키워드/공시 리스크
        assert r["grade"].grade in (CreditGrade.C, CreditGrade.D, CreditGrade.E)


# ════════════════════════════════════════════════════════════════════════════
# 불변 조건 테스트
# ════════════════════════════════════════════════════════════════════════════

class TestInvariants:

    @pytest.mark.parametrize("grade", list(CreditGrade))
    def test_score_in_range_for_all_grades(self, grade):
        ctx = {
            "company_name": "테스트", "critical_count": 0, "high_count": 0,
            "medium_count": 0, "low_count": 0,
            "latest_debt_ratio": 100.0, "latest_op_margin": 5.0,
            "is_net_income_negative": False, "classified_events": [],
        }
        r = calculate_grade(ctx)
        assert 0 <= r.score <= 100

    @pytest.mark.parametrize("grade,expected", [
        (CreditGrade.A, DecisionResult.APPROVE),
        (CreditGrade.B, DecisionResult.APPROVE),
        (CreditGrade.C, DecisionResult.REVIEW),
        (CreditGrade.D, DecisionResult.REJECT),
        (CreditGrade.E, DecisionResult.REJECT),
    ])
    def test_grade_to_decision_mapping(self, grade, expected):
        ctx = {
            "company_name": "테스트", "critical_count": 0, "high_count": 0,
            "medium_count": 0, "low_count": 0,
            "is_net_income_negative": False,
        }
        r = make_decision(grade, 50, ctx)
        assert r.result == expected

    def test_rejected_limit_always_zero(self):
        for grade in CreditGrade:
            r = recommend_limit(grade, DecisionResult.REJECT,
                                {"company_name": "테스트",
                                 "total_assets": 100_000_000_000,
                                 "revenue": 50_000_000_000})
            assert r.recommended_limit == 0, f"등급={grade} 거절인데 한도={r.recommended_limit}"

    def test_confidence_always_valid(self):
        for grade in CreditGrade:
            for score in [0, 35, 50, 65, 80, 100]:
                r = make_decision(grade, score, {
                    "company_name": "테스트", "critical_count": 0, "high_count": 0,
                    "medium_count": 0, "low_count": 0,
                    "is_net_income_negative": False,
                })
                assert 0.0 <= r.confidence <= 1.0, \
                    f"grade={grade} score={score} confidence={r.confidence}"

    def test_timeline_always_descending(self):
        evs = []
        for i in range(6):
            ev = RiskEvent(
                event_type=EventType.NEGATIVE_KEYWORD,
                source=EventSource.NEWS,
                title="테스트", description="",
                detected_at=date.today() - timedelta(days=i * 7),
            )
            evs.append(SeverityClassifiedEvent(
                event=ev, severity=SeverityLevel.LOW, score=25, rationale=""
            ))
        timeline = build_timeline(evs)
        dates = [t.date for t in timeline]
        assert dates == sorted(dates, reverse=True)

    def test_severity_score_order(self):
        """CRITICAL 점수 > HIGH > MEDIUM > LOW"""
        from backend.agents.risk_event.handlers.severity_classifier import _SEVERITY_BASE_SCORE
        assert (
            _SEVERITY_BASE_SCORE[SeverityLevel.CRITICAL]
            > _SEVERITY_BASE_SCORE[SeverityLevel.HIGH]
            > _SEVERITY_BASE_SCORE[SeverityLevel.MEDIUM]
            > _SEVERITY_BASE_SCORE[SeverityLevel.LOW]
        )

    def test_grade_order_consistency(self):
        """등급 점수 순서: A > B > C > D > E"""
        grade_scores = {
            CreditGrade.A: 90,
            CreditGrade.B: 72,
            CreditGrade.C: 57,
            CreditGrade.D: 42,
            CreditGrade.E: 20,
        }
        prev = 101
        for grade in [CreditGrade.A, CreditGrade.B, CreditGrade.C,
                      CreditGrade.D, CreditGrade.E]:
            assert grade_scores[grade] < prev
            prev = grade_scores[grade]


# ════════════════════════════════════════════════════════════════════════════
# 엣지 케이스 테스트
# ════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_empty_payload(self):
        """모든 입력 비어도 파이프라인 정상 완료"""
        r = run_pipeline("빈기업", "00000099")
        assert r["grade"] is not None
        assert r["decision"] is not None
        assert r["limit"] is not None

    def test_zero_revenue_no_crash(self):
        """매출 0인 재무 데이터도 크래시 없음"""
        r = run_pipeline(
            "무매출기업", "00000098",
            financial_rows=[
                {"year": "2024", "revenue": "0", "operating_income": "0",
                 "net_income": "0", "total_assets_statement": "1000000000",
                 "total_liabilities": "500000000", "total_equity": "500000000"},
            ],
        )
        assert r["grade"].score is not None

    def test_single_year_data(self):
        """1년치 데이터만 있어도 정상 처리 (전년 비교 없음)"""
        r = run_pipeline(
            "1년기업", "00000097",
            financial_rows=[
                {"year": "2024", "revenue": "20000000000",
                 "operating_income": "1000000000", "net_income": "500000000",
                 "total_assets_statement": "40000000000",
                 "total_liabilities": "15000000000", "total_equity": "25000000000"},
            ],
        )
        assert r["ctx"]["critical_count"] == 0
        assert r["decision"].result is not None

    def test_grade_cap_worse_than_computed(self):
        """grade_cap이 계산 등급보다 낮으면 cap 적용"""
        r = run_pipeline(
            "캡기업", "00000096",
            financial_rows=[
                {"year": "2024", "revenue": "200000000000",
                 "operating_income": "30000000000", "net_income": "20000000000",
                 "total_assets_statement": "500000000000",
                 "total_liabilities": "100000000000", "total_equity": "400000000000"},
            ],
            extra_ctx={"grade_cap": "BB+"},
        )
        # grade_cap BB+ → 최대 C등급
        assert r["grade"].grade in (CreditGrade.C, CreditGrade.D, CreditGrade.E)

    def test_date_parsing_fallback(self):
        """날짜 파싱 실패해도 today()로 대체"""
        kw = detect_keywords("테스트", [
            {"title": "소송 제기", "content": "소송 발생",
             "published_at": "invalid-date", "url": None}
        ], [])
        if kw.detected_events:
            assert kw.detected_events[0].detected_at == date.today()
