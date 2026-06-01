"""Risk Event Agent 핸들러 단위 테스트 (고도화 포함)

실행: python -m pytest tests/unit/test_risk_event_handlers.py -v
"""

from __future__ import annotations

from datetime import date

import pytest

# ─── 테스트용 모델 임포트 ─────────────────────────────────────────────────────
from backend.agents.risk_event.models import (
    EventSource, EventType, RiskEvent, SeverityLevel,
)
from backend.agents.risk_event.handlers.keyword_detector import detect_keywords
from backend.agents.risk_event.handlers.disclosure_detector import detect_disclosure_anomalies
from backend.agents.risk_event.handlers.legal_risk_detector import detect_legal_risks
from backend.agents.risk_event.handlers.financial_anomaly_detector import detect_financial_anomalies
from backend.agents.risk_event.handlers.severity_classifier import classify_severity
from backend.agents.risk_event.handlers.timeline_builder import build_timeline


# ════════════════════════════════════════════════════════════════════════════
# 픽스처
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def news_with_risk():
    return [
        {
            "title": "삼성전자 부도 위기설 확산",
            "content": "삼성전자가 소송에 휘말리며 경영 위기가 가시화되고 있다.",
            "published_at": "2026-05-01",
            "url": "https://example.com/1",
        },
        {
            "title": "삼성전자 2분기 실적 호조",
            "content": "삼성전자가 2분기 매출 성장세를 기록했다.",
            "published_at": "2026-05-10",
            "url": "https://example.com/2",
        },
    ]

@pytest.fixture
def disclosure_with_risk():
    return [
        {
            "title": "단기차입금 증가 관련 주요사항보고서",
            "content": "당사는 운영자금 확보를 위해 단기차입금을 증가하였습니다.",
            "disclosed_at": "2026-05-01",
            "url": "https://dart.fss.or.kr/example",
        },
        {
            "title": "최대주주 변경 공시",
            "content": "최대주주 변경으로 경영권 이전이 발생하였습니다.",
            "disclosed_at": "2026-04-20",
        },
    ]

@pytest.fixture
def court_data():
    return [
        {
            "title": "파산선고 결정",
            "content": "OO법원은 A사에 대해 파산선고를 내렸다.",
            "announced_at": "2026-05-15",
            "url": "https://court.go.kr/1",
        },
        {
            "title": "채권 가압류 결정",
            "content": "B사 채권에 대한 가압류 결정이 내려졌다.",
            "announced_at": "2026-05-10",
            "url": "https://court.go.kr/2",
        },
    ]

@pytest.fixture
def financial_rows_normal():
    """정상 재무 데이터 (이상 없음)"""
    return [
        {"year": "2022", "revenue": "100000000000", "operating_income": "8000000000",
         "net_income": "5000000000", "total_assets_statement": "200000000000",
         "total_liabilities": "80000000000", "total_equity": "120000000000"},
        {"year": "2023", "revenue": "110000000000", "operating_income": "9000000000",
         "net_income": "6000000000", "total_assets_statement": "220000000000",
         "total_liabilities": "85000000000", "total_equity": "135000000000"},
        {"year": "2024", "revenue": "115000000000", "operating_income": "9500000000",
         "net_income": "6500000000", "total_assets_statement": "230000000000",
         "total_liabilities": "88000000000", "total_equity": "142000000000"},
    ]

@pytest.fixture
def financial_rows_risky():
    """위험 재무 데이터 (부채비율 급증 + 적자 전환)"""
    return [
        {"year": "2022", "revenue": "100000000000", "operating_income": "5000000000",
         "net_income": "3000000000", "total_assets_statement": "150000000000",
         "total_liabilities": "60000000000", "total_equity": "90000000000"},
        {"year": "2023", "revenue": "90000000000", "operating_income": "-2000000000",
         "net_income": "-5000000000", "total_assets_statement": "130000000000",
         "total_liabilities": "110000000000", "total_equity": "20000000000"},
        {"year": "2024", "revenue": "70000000000", "operating_income": "-8000000000",
         "net_income": "-10000000000", "total_assets_statement": "100000000000",
         "total_liabilities": "120000000000", "total_equity": "-20000000000"},
    ]

@pytest.fixture
def financial_rows_capital_impaired():
    """자본잠식 재무 데이터"""
    return [
        {"year": "2023", "revenue": "50000000000", "operating_income": "-3000000000",
         "net_income": "-5000000000", "total_assets_statement": "80000000000",
         "total_liabilities": "90000000000", "total_equity": "-10000000000"},
    ]


# ════════════════════════════════════════════════════════════════════════════
# R-001 | 키워드 탐지
# ════════════════════════════════════════════════════════════════════════════

class TestKeywordDetector:

    def test_detects_news_risk_keyword(self, news_with_risk):
        result = detect_keywords("삼성전자", news_with_risk, [])
        assert len(result.detected_events) >= 1
        sources = [e.source for e in result.detected_events]
        assert EventSource.NEWS in sources

    def test_detects_disclosure_risk_keyword(self, disclosure_with_risk):
        result = detect_keywords("삼성전자", [], disclosure_with_risk)
        assert len(result.detected_events) >= 1
        sources = [e.source for e in result.detected_events]
        assert EventSource.DISCLOSURE in sources

    def test_no_events_on_clean_data(self):
        result = detect_keywords("청정기업", [
            {"title": "청정기업 매출 성장", "content": "양호한 실적을 기록했다.",
             "published_at": "2026-01-01", "url": None}
        ], [])
        assert len(result.detected_events) == 0

    def test_empty_inputs(self):
        result = detect_keywords("테스트", [], [])
        assert result.company_name == "테스트"
        assert result.detected_events == []

    def test_no_duplicate_category(self, news_with_risk):
        """같은 카테고리 키워드가 여러 개 있어도 카테고리당 1건만 탐지"""
        news = [{"title": "소송 제기 및 가압류 결정",
                 "content": "소송과 압류가 동시에 발생했다.",
                 "published_at": "2026-01-01", "url": None}]
        result = detect_keywords("테스트", news, [])
        event_types = [e.event_type for e in result.detected_events]
        # 같은 카테고리 중복 없어야 함
        assert len(event_types) == len(set(
            e.description.split("]")[0] for e in result.detected_events
        ))

    def test_company_name_stored(self, news_with_risk):
        result = detect_keywords("삼성전자", news_with_risk, [])
        assert result.company_name == "삼성전자"

    def test_analyzed_at_is_today(self):
        result = detect_keywords("테스트", [], [])
        assert result.analyzed_at == date.today()


# ════════════════════════════════════════════════════════════════════════════
# R-003 | 공시 이상 탐지
# ════════════════════════════════════════════════════════════════════════════

class TestDisclosureDetector:

    def test_detects_large_borrowing(self, disclosure_with_risk):
        result = detect_disclosure_anomalies("삼성전자", "00000001", disclosure_with_risk)
        titles = [e.title for e in result.anomalies]
        assert any("대규모 차입" in t for t in titles)

    def test_detects_major_shareholder_change(self, disclosure_with_risk):
        result = detect_disclosure_anomalies("삼성전자", "00000001", disclosure_with_risk)
        titles = [e.title for e in result.anomalies]
        assert any("최대주주 변경" in t for t in titles)

    def test_empty_disclosure(self):
        result = detect_disclosure_anomalies("테스트", "00000001", [])
        assert result.anomalies == []

    def test_no_false_positives_on_clean_disclosure(self):
        result = detect_disclosure_anomalies("테스트", "00000001", [
            {"title": "정기 사업보고서", "content": "당사 사업현황은 양호합니다.",
             "disclosed_at": "2026-01-01"}
        ])
        assert result.anomalies == []

    def test_corp_code_stored(self, disclosure_with_risk):
        result = detect_disclosure_anomalies("삼성전자", "00000001", disclosure_with_risk)
        assert result.corp_code == "00000001"


# ════════════════════════════════════════════════════════════════════════════
# R-006 | 법적 리스크 탐지
# ════════════════════════════════════════════════════════════════════════════

class TestLegalRiskDetector:

    def test_detects_bankruptcy(self, court_data):
        result = detect_legal_risks("테스트", court_data)
        titles = [e.title for e in result.legal_risks]
        assert any("파산" in t for t in titles)

    def test_detects_provisional_seizure(self, court_data):
        result = detect_legal_risks("테스트", court_data)
        titles = [e.title for e in result.legal_risks]
        assert any("가압류" in t for t in titles)

    def test_empty_court_data(self):
        result = detect_legal_risks("테스트", [])
        assert result.legal_risks == []

    def test_event_source_is_court(self, court_data):
        result = detect_legal_risks("테스트", court_data)
        assert all(e.source == EventSource.COURT for e in result.legal_risks)

    def test_event_type_is_legal_risk(self, court_data):
        result = detect_legal_risks("테스트", court_data)
        assert all(e.event_type == EventType.LEGAL_RISK for e in result.legal_risks)


# ════════════════════════════════════════════════════════════════════════════
# R-NEW | 재무 이상 탐지
# ════════════════════════════════════════════════════════════════════════════

class TestFinancialAnomalyDetector:

    def test_no_anomaly_on_normal_data(self, financial_rows_normal):
        result = detect_financial_anomalies("정상기업", "00000001", financial_rows_normal)
        assert len(result.anomalies) == 0

    def test_detects_net_income_negative_turn(self, financial_rows_risky):
        result = detect_financial_anomalies("위험기업", "00000002", financial_rows_risky)
        titles = [e.title for e in result.anomalies]
        assert any("적자 전환" in t for t in titles)

    def test_detects_capital_impaired(self, financial_rows_capital_impaired):
        result = detect_financial_anomalies("잠식기업", "00000003", financial_rows_capital_impaired)
        titles = [e.title for e in result.anomalies]
        assert any("자본잠식" in t for t in titles)

    def test_detects_debt_ratio_spike(self, financial_rows_risky):
        result = detect_financial_anomalies("위험기업", "00000002", financial_rows_risky)
        titles = [e.title for e in result.anomalies]
        assert any("부채비율 급증" in t for t in titles)

    def test_detects_revenue_decline(self, financial_rows_risky):
        result = detect_financial_anomalies("위험기업", "00000002", financial_rows_risky)
        titles = [e.title for e in result.anomalies]
        assert any("매출 감소" in t for t in titles)

    def test_latest_debt_ratio_populated(self, financial_rows_risky):
        result = detect_financial_anomalies("위험기업", "00000002", financial_rows_risky)
        assert result.latest_debt_ratio is not None
        assert result.latest_debt_ratio < 0  # 자본잠식 (음수 자본)

    def test_is_net_income_negative_flag(self, financial_rows_risky):
        result = detect_financial_anomalies("위험기업", "00000002", financial_rows_risky)
        assert result.is_net_income_negative is True

    def test_empty_rows(self):
        result = detect_financial_anomalies("테스트", "00000001", [])
        assert result.anomalies == []
        assert result.latest_debt_ratio is None

    def test_years_analyzed(self, financial_rows_normal):
        result = detect_financial_anomalies("정상기업", "00000001", financial_rows_normal)
        assert sorted(result.years_analyzed) == [2022, 2023, 2024]


# ════════════════════════════════════════════════════════════════════════════
# R-004 | 심각도 분류 (고도화)
# ════════════════════════════════════════════════════════════════════════════

class TestSeverityClassifier:

    def _make_event(self, event_type, title, description="테스트", delta=None):
        return RiskEvent(
            event_type=event_type,
            source=EventSource.NEWS,
            title=title,
            description=description,
            detected_at=date.today(),
            delta_value=delta,
        )

    # 법적 리스크 세분화
    def test_legal_bankruptcy_is_critical(self):
        ev = self._make_event(EventType.LEGAL_RISK, "법적 리스크: 파산")
        result = classify_severity(ev)
        assert result.severity == SeverityLevel.CRITICAL

    def test_legal_seizure_is_high(self):
        ev = self._make_event(EventType.LEGAL_RISK, "법적 리스크: 가압류")
        result = classify_severity(ev)
        assert result.severity == SeverityLevel.HIGH

    def test_legal_auction_is_high(self):
        ev = self._make_event(EventType.LEGAL_RISK, "법적 리스크: 경매")
        result = classify_severity(ev)
        assert result.severity == SeverityLevel.HIGH

    # 재무 이상 세분화
    def test_financial_capital_impaired_is_critical(self):
        ev = self._make_event(EventType.FINANCIAL_ANOMALY, "자본잠식 (2024)")
        result = classify_severity(ev)
        assert result.severity == SeverityLevel.CRITICAL

    def test_financial_net_loss_turn_is_critical(self):
        ev = self._make_event(EventType.FINANCIAL_ANOMALY, "당기순이익 적자 전환 (2024)")
        result = classify_severity(ev)
        assert result.severity == SeverityLevel.CRITICAL

    def test_financial_large_debt_spike_is_high(self):
        ev = self._make_event(EventType.FINANCIAL_ANOMALY, "부채비율 급증 (2023→2024)", delta=60.0)
        result = classify_severity(ev)
        assert result.severity == SeverityLevel.HIGH

    def test_financial_small_debt_spike_is_medium(self):
        ev = self._make_event(EventType.FINANCIAL_ANOMALY, "부채비율 급증 (2023→2024)", delta=30.0)
        result = classify_severity(ev)
        assert result.severity == SeverityLevel.MEDIUM

    def test_score_range(self):
        """모든 심각도 점수는 0-100 범위 내"""
        for level, title in [
            (EventType.LEGAL_RISK, "법적 리스크: 파산"),
            (EventType.FINANCIAL_ANOMALY, "자본잠식 (2024)"),
            (EventType.NEGATIVE_SENTIMENT, "부정 뉴스"),
            (EventType.NEGATIVE_KEYWORD, "부정 키워드 탐지: 부도"),
        ]:
            ev = self._make_event(level, title)
            result = classify_severity(ev)
            assert 0 <= result.score <= 100, f"{title} score={result.score} out of range"

    def test_rationale_not_empty(self):
        ev = self._make_event(EventType.NEGATIVE_KEYWORD, "부정 키워드 탐지: 횡령")
        result = classify_severity(ev)
        assert result.rationale != ""


# ════════════════════════════════════════════════════════════════════════════
# R-005 | 타임라인
# ════════════════════════════════════════════════════════════════════════════

class TestTimelineBuilder:

    def _make_classified(self, severity, days_ago):
        from datetime import timedelta
        ev = RiskEvent(
            event_type=EventType.NEGATIVE_KEYWORD,
            source=EventSource.NEWS,
            title="테스트 이벤트",
            description="설명",
            detected_at=date.today() - timedelta(days=days_ago),
        )
        from backend.agents.risk_event.models import SeverityClassifiedEvent
        return SeverityClassifiedEvent(
            event=ev, severity=severity, score=50, rationale="테스트"
        )

    def test_empty_events_returns_empty(self):
        assert build_timeline([]) == []

    def test_latest_date_first(self):
        events = [
            self._make_classified(SeverityLevel.LOW, 5),
            self._make_classified(SeverityLevel.HIGH, 1),
            self._make_classified(SeverityLevel.MEDIUM, 3),
        ]
        timeline = build_timeline(events)
        dates = [t.date for t in timeline]
        assert dates == sorted(dates, reverse=True)

    def test_same_date_grouped(self):
        events = [
            self._make_classified(SeverityLevel.LOW, 0),
            self._make_classified(SeverityLevel.HIGH, 0),
        ]
        timeline = build_timeline(events)
        assert len(timeline) == 1
        assert len(timeline[0].events) == 2

    def test_severity_order_within_date(self):
        """같은 날짜 내 CRITICAL이 LOW보다 앞에 와야 함"""
        from backend.agents.risk_event.models import SeverityClassifiedEvent
        d = date.today()
        events = []
        for sev in [SeverityLevel.LOW, SeverityLevel.CRITICAL, SeverityLevel.MEDIUM]:
            ev = RiskEvent(
                event_type=EventType.NEGATIVE_KEYWORD,
                source=EventSource.NEWS,
                title="테스트",
                description="",
                detected_at=d,
            )
            events.append(SeverityClassifiedEvent(
                event=ev, severity=sev, score=50, rationale=""
            ))
        timeline = build_timeline(events)
        severities = [e.severity for e in timeline[0].events]
        assert severities[0] == SeverityLevel.CRITICAL
