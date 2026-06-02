"""
FinAgent-SME 멀티 에이전트 공유 State 스키마.

에이전트 실행 순서:
    Orchestrator
        → Financial Analyst Agent  → FinancialResult 적재
        → Industry Analyst Agent   → IndustryResult  적재
        → (Risk Event / Multimodal Document Agent)
        → XAI / Decision Agent     → 최종 등급 산출

모든 필드는 `backend.tools.financial` / `backend.tools.industry` 반환값과 1:1 대응합니다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Financial Agent 출력 서브 모델

class FinancialRatios(BaseModel):
    """calc_financial_ratios 반환값 (15개 비율, 단일 숫자)."""

    # 안정성
    debt_ratio:         float           # 부채비율 (부채/자본)
    current_ratio:      float           # 유동비율 (유동자산/유동부채)
    quick_ratio:        float           # 당좌비율 ((유동자산-재고)/유동부채)
    borrow_dep:         float           # 차입금의존도 (총차입금/총자산)
    interest_coverage:  float | None    # 이자보상배율 (이자비용=0이면 null)

    # 활동성
    receivable_turnover: float          # 매출채권회전율 (회)
    asset_turnover:      float          # 총자산회전율 (배)
    payable_turnover:    float          # 매입채무회전율 (회)

    # 수익성
    roa:        float                   # ROA (순이익/총자산)
    op_margin:  float                   # 영업이익률 (영업이익/매출액)
    cogs_ratio: float                   # 매출원가율 (매출원가/매출액)

    # 현금흐름
    ocf_to_sales:      float            # OCF/매출액
    ocf_to_net_income: float | None     # OCF/순이익 (순이익=0이면 null)
    fcf:               float            # FCF (영업현금흐름 - 자본적지출)
    fcf_to_sales:      float            # FCF/매출액


class AltmanZ(BaseModel):
    """calc_altman_z_prime 반환값."""

    z_prime:    float                           # Z'-Score
    zone:       str                             # "Safe" | "Grey" | "Distress"
    components: dict[str, float]                # X1~X5 구성요소


class TrendYoY(BaseModel):
    """trend_analysis.yoy — 연도별 YoY 변화량 리스트."""

    debt_ratio:     list[float] = Field(default_factory=list)   # 부채비율 변화량
    op_margin:      list[float] = Field(default_factory=list)   # 영업이익률 변화량
    revenue_growth: list[float] = Field(default_factory=list)   # 매출액증가율
    asset_growth:   list[float] = Field(default_factory=list)   # 총자산증가율


class TrendHistoryItem(BaseModel):
    """trend_analysis.history 단일 연도 항목."""

    year:         int
    debt_ratio:   float
    op_margin:    float
    icr:          float | None      # 이자보상배율 (이자비용=0이면 null)
    revenue:      float             # 매출액 (원)
    net_income:   float             # 당기순이익 (원)
    total_assets: float             # 총자산 (원)
    ocf:          float             # 영업현금흐름 (원)


class TrendAnalysis(BaseModel):
    """trend_analysis 반환값."""

    flags:   list[str]                                  # YoY·절댓값 플래그 목록
    yoy:     TrendYoY                                   # YoY 변화량
    history: list[TrendHistoryItem]                     # 연도별 히스토리


class GrowthRatios(BaseModel):
    """trend_analysis.growth_ratios — 성장성 지표 (이크레더블 성장성 카테고리)."""

    revenue_growth:        float | None = None   # 매출액증가율 (최신 YoY)
    asset_growth:          float | None = None   # 총자산증가율 (최신 YoY)
    net_income_growth:     float | None = None   # 순이익증가율 (전기 순이익=0이면 null)
    tangible_asset_growth: float | None = None   # 유형자산증가율 (현재 미구현, 항상 null)


class RiskFilter(BaseModel):
    """apply_risk_filters 반환값 — 신용등급 상한(ceiling)."""

    grade_cap:         str | None               # "CCC"|"B"|"B+"|"BB+"|null
    triggered_filters: list[str]                # 발동된 필터 키 목록
    filter_detail:     dict[str, str]           # 필터별 판단 근거 상세


class FinancialResult(BaseModel):
    """
    Financial Analyst Agent 최종 출력 (`backend.tools.prompts.financial` 출력 구조 기준).
    오케스트레이터는 `FinancialAnalystAgent.run()` 결과를 이 모델에 맞는 형태로 적재합니다.
    """

    ratios:         FinancialRatios
    altman_z:       AltmanZ
    trend_analysis: TrendAnalysis
    growth_ratios:  GrowthRatios
    risk_filter:    RiskFilter
    summary_kor:    str     # 8개 태그 단락: [안정성][유동성][수익성][활동성][현금흐름][성장성·추세][부도예측][리스크 필터]


# Industry Agent 출력 서브 모델

class IndustryAvg(BaseModel):
    """get_industry_avg_ratios 반환값 — 동종 중소기업 평균 8종 비율."""

    op_margin:           float | None = None    # 평균 영업이익률
    debt_ratio:          float | None = None    # 평균 부채비율
    current_ratio:       float | None = None    # 평균 유동비율
    interest_coverage:   float | None = None    # 평균 이자보상배율
    borrow_dep:          float | None = None    # 평균 차입금의존도
    receivable_turnover: float | None = None    # 평균 매출채권회전율
    asset_turnover:      float | None = None    # 평균 총자산회전율
    sales_growth:        float | None = None    # 평균 매출액증가율


class PeerItem(BaseModel):
    """peer_comparison 단일 지표 비교 결과."""

    company:  float | None                      # 대상 기업 값 (company_ratios 미전달 시 null)
    avg:      float | None                      # 산업 평균 값
    judgment: str                               # "better" | "in-line" | "worse" | "n/a"


class OutlookDetail(BaseModel):
    """get_industry_outlook 반환값 — 생산·재고·출하 지수 YoY."""

    production_index_yoy: float | None = None   # 생산지수 YoY (제조·서비스·농업)
    inventory_index_yoy:  float | None = None   # 재고지수 YoY (제조업만 해당)
    shipment_index_yoy:   float | None = None   # 출하지수 YoY (제조업만 해당)


class BusinessCycle(BaseModel):
    """get_business_cycle 반환값 — ECOS 선행·동행지수 기반 경기 국면."""

    phase:             str      # "확장" | "회복" | "둔화" | "수축"
    leading_trend:     str      # "rising" | "falling"
    coincident_trend:  str      # "rising" | "falling"
    leading_latest:    float    # 선행지수 순환변동치 최신값
    coincident_latest: float    # 동행지수 순환변동치 최신값


class MacroSignals(BaseModel):
    """get_macro_indicators 반환값 — ECOS 기준금리·환율·업종 환율민감도."""

    base_rate:      float               # 기준금리 (%)
    usd_krw:        float               # 원달러환율
    rate_trend:     str                 # "rising" | "falling" | "stable"
    fx_sensitivity: str | None = None   # 업종 환율민감도 분류 (수출형·수입의존형 등)
    fx_direction:   str | None = None   # "원화 약세" | "원화 강세" | "원화 중립"
    fx_impact:      str | None = None   # 업종별 환율 영향 자연어 해석


class IndustryResult(BaseModel):
    """
    Industry Analyst Agent 최종 출력 (`backend.tools.prompts.industry` 출력 구조 기준).
    오케스트레이터는 `IndustryAnalystAgent.run()` 결과를 이 모델에 맞는 형태로 적재합니다.
    """

    corp_name:       str
    ksic_code:       str                        # 전체 KSIC 문자열 (예: "P 교육 서비스업")
    sector_note:     str                        # 업종 고유 재무구조 특성 메모
    industry_avg:    IndustryAvg
    peer_comparison: dict[str, PeerItem]        # 키: 지표명 (8개)
    outlook_score:   str                        # "Low" | "Medium" | "High"
    outlook_source:  str                        # 데이터 출처 (KOSIS 등)
    outlook_detail:  OutlookDetail
    business_cycle:  BusinessCycle
    macro_signals:   MacroSignals
    summary_kor:     str    # 5개 태그 단락: [업종 소속][동종업계 비교][업황][경기 국면][거시환경]


# 공유 State

class CreditState(BaseModel):
    """
    FinAgent-SME 멀티 에이전트 공유 State.

    Orchestrator가 각 에이전트 실행 후 결과를 적재하며,
    XAI/Decision Agent가 모든 필드를 참조해 최종 등급을 산출합니다.

    플랫 필드(financial_ratios, growth_ratios 등)는
    XAI/Decision Agent가 nested 구조를 파싱하지 않고 바로 접근할 수 있도록
    FinancialResult/IndustryResult의 주요 필드를 최상위에 복사합니다.
    """

    # ── 입력 ──────────────────────────────────────────────────────────────
    corp_code:   str
    corp_name:   str | None = None
    target_year: int = 2024

    # ── Financial Agent 결과 ──────────────────────────────────────────────
    financial_result: FinancialResult | None = None

    # 플랫 필드 — FinancialResult 적재 시 함께 세팅
    financial_ratios:  FinancialRatios | None = None   # = financial_result.ratios
    growth_ratios:     GrowthRatios    | None = None   # = financial_result.growth_ratios
    altman_z:          AltmanZ         | None = None   # = financial_result.altman_z
    trend_analysis:    TrendAnalysis   | None = None   # = financial_result.trend_analysis
    risk_filter:       RiskFilter      | None = None   # = financial_result.risk_filter
    grade_cap:         str | None      = None          # = risk_filter.grade_cap (등급 상한)
    financial_summary: str | None      = None          # = financial_result.summary_kor

    # ── Industry Agent 결과 ───────────────────────────────────────────────
    industry_result: IndustryResult | None = None

    # 플랫 필드 — IndustryResult 적재 시 함께 세팅
    ksic_code:        str | None           = None   # = industry_result.ksic_code
    outlook_score:    str | None           = None   # = industry_result.outlook_score
    business_cycle:   BusinessCycle | None = None   # = industry_result.business_cycle
    macro_signals:    MacroSignals  | None = None   # = industry_result.macro_signals
    industry_summary: str | None           = None   # = industry_result.summary_kor

    # ── 기타 에이전트 결과 (추후 적재) ───────────────────────────────────
    risk_event_result: dict[str, Any] | None = None   # Risk Event Agent
    document_result:   dict[str, Any] | None = None   # Multimodal Document Agent

    # ── XAI / Decision Agent 결과 ─────────────────────────────────────────
    final_grade:      str | None           = None   # 최종 신용등급
    decision_summary: str | None           = None   # 의사결정 요약
    xai_explanation:  dict[str, Any] | None = None  # XAI 근거

    class Config:
        extra = "allow"   # 향후 에이전트 확장 시 유연하게 수용


# Orchestrator 적재 헬퍼

def load_financial_result(state: CreditState, raw_json: dict) -> CreditState:
    """
    Financial Agent 출력 JSON을 파싱해 CreditState에 적재한다.

    사용 예:
        raw = {
            "ratios": {...},
            "altman_z": {...},
            "trend_analysis": {...},
            "growth_ratios": {...},
            "risk_filter": {...},
            "summary_kor": "...",
        }
        state = load_financial_result(state, raw)
    """
    fin = FinancialResult(
        ratios         = FinancialRatios(**raw_json["ratios"]),
        altman_z       = AltmanZ(**raw_json["altman_z"]),
        trend_analysis = TrendAnalysis(
            flags   = raw_json["trend_analysis"]["flags"],
            yoy     = TrendYoY(**raw_json["trend_analysis"]["yoy"]),
            history = [TrendHistoryItem(**h) for h in raw_json["trend_analysis"]["history"]],
        ),
        growth_ratios  = GrowthRatios(**raw_json["growth_ratios"]),
        risk_filter    = RiskFilter(**raw_json["risk_filter"]),
        summary_kor    = raw_json["summary_kor"],
    )

    state.financial_result  = fin
    state.financial_ratios  = fin.ratios
    state.growth_ratios     = fin.growth_ratios
    state.altman_z          = fin.altman_z
    state.trend_analysis    = fin.trend_analysis
    state.risk_filter       = fin.risk_filter
    state.grade_cap         = fin.risk_filter.grade_cap
    state.financial_summary = fin.summary_kor
    return state


def load_industry_result(state: CreditState, raw_json: dict) -> CreditState:
    """
    Industry Agent 출력 JSON을 파싱해 CreditState에 적재한다.

    사용 예:
        raw = {
            "corp_name": "...",
            "ksic_code": "...",
            "sector_note": "...",
            "industry_avg": {...},
            "peer_comparison": {...},
            "outlook_score": "...",
            "outlook_source": "...",
            "outlook_detail": {...},
            "business_cycle": {...},
            "macro_signals": {...},
            "summary_kor": "...",
        }
        state = load_industry_result(state, raw)
    """
    ind = IndustryResult(
        corp_name       = raw_json["corp_name"],
        ksic_code       = raw_json["ksic_code"],
        sector_note     = raw_json["sector_note"],
        industry_avg    = IndustryAvg(**raw_json["industry_avg"]),
        peer_comparison = {
            k: PeerItem(**v) for k, v in raw_json["peer_comparison"].items()
        },
        outlook_score   = raw_json["outlook_score"],
        outlook_source  = raw_json["outlook_source"],
        outlook_detail  = OutlookDetail(**raw_json["outlook_detail"]),
        business_cycle  = BusinessCycle(**raw_json["business_cycle"]),
        macro_signals   = MacroSignals(**raw_json["macro_signals"]),
        summary_kor     = raw_json["summary_kor"],
    )

    state.industry_result  = ind
    state.corp_name        = ind.corp_name
    state.ksic_code        = ind.ksic_code
    state.outlook_score    = ind.outlook_score
    state.business_cycle   = ind.business_cycle
    state.macro_signals    = ind.macro_signals
    state.industry_summary = ind.summary_kor
    return state
