"""
CreditState — FinAgent-SME 공유 상태 정의

Financial Analyst Agent, Industry Agent 두 에이전트가
공유하는 LangGraph State입니다.

흐름:
  Orchestrator
    ├─ Financial Analyst Agent → financial_ratios, altman_z, trend_analysis,
    │                            risk_filter, financial_summary
    └─ Industry Agent          → ksic_code, sector_note, industry_avg,
                                 peer_comparison, outlook, business_cycle,
                                 macro_signals, industry_summary
"""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict
from langgraph.graph.message import add_messages


class CreditState(TypedDict):
    # ── 입력 ────────────────────────────────────────────────────────────────
    corp_code:      str        # DART 8자리 고유번호
    corp_name:      str        # 회사명 (get_financial_statements에서 확인)
    target_year:    int        # 비율·Altman Z' 계산 기준 연도 (최신 연도)
    analysis_years: list[int]  # 추세 분석 대상 연도 목록 (예: [2022, 2023, 2024])

    # ── Financial Analyst Agent 결과 ────────────────────────────────────────
    financial_ratios: Optional[dict]
    # 15개 재무비율
    # {debt_ratio, current_ratio, quick_ratio, borrow_dep,
    #  interest_coverage (float|None, 이자비용=0 시),
    #  receivable_turnover, asset_turnover, payable_turnover,
    #  roa, op_margin, cogs_ratio, ocf_to_sales,
    #  ocf_to_net_income (float|None, 당기순이익=0 시),
    #  fcf, fcf_to_sales}

    altman_z: Optional[dict]
    # {z_prime: float, zone: "Safe"|"Grey"|"Distress",
    #  components: {X1, X2, X3, X4, X5}}

    trend_analysis: Optional[dict]
    # {flags: list[str],  # "{year}_data_missing" 포함 가능
    #  yoy: {debt_ratio, op_margin, revenue_growth, asset_growth},
    #  history: list[{year, debt_ratio, op_margin,
    #                 icr (float|None, 이자비용=0 시),
    #                 revenue, net_income, total_assets, ocf}]}

    risk_filter: Optional[dict]
    # {grade_cap: str|None, triggered_filters: list[str], filter_detail: dict}

    financial_summary: Optional[str]
    # summary_kor
    # [안정성][유동성][수익성][활동성][현금흐름][성장성·추세][부도예측][리스크 필터]

    # ── Industry Agent 결과 ─────────────────────────────────────────────────
    ksic_code: Optional[str]
    # KSIC 대분류 전체 문자열 (예: "P 교육 서비스업", "C 제조업")

    sector_note: Optional[str]
    # 업종별 재무·구조적 특성 주의사항 텍스트

    industry_avg: Optional[dict]
    # 동종업계 중소기업 평균 8종
    # {op_margin, debt_ratio, current_ratio, interest_coverage,
    #  borrow_dep, receivable_turnover, asset_turnover, sales_growth}

    peer_comparison: Optional[dict]
    # 지표별 기업 vs 산업평균 비교
    # {"<지표명>": {company: float|None, avg: float,
    #               judgment: "better"|"in-line"|"worse"|"n/a"}}

    outlook: Optional[dict]
    # 업황 신호
    # {outlook_score: "Low"|"Medium"|"High", outlook_source: str,
    #  production_index_yoy: float|None,
    #  inventory_index_yoy:  float|None,
    #  shipment_index_yoy:   float|None}

    business_cycle: Optional[dict]
    # 경기 국면
    # {phase: "확장"|"회복"|"둔화"|"수축",
    #  leading_trend: "rising"|"falling",
    #  coincident_trend: "rising"|"falling",
    #  leading_latest: float, coincident_latest: float}

    macro_signals: Optional[dict]
    # 거시 지표
    # {base_rate: float, usd_krw: float,
    #  rate_trend: "rising"|"falling"|"stable",
    #  fx_sensitivity: str|None, fx_direction: str|None, fx_impact: str|None}

    industry_summary: Optional[str]
    # summary_kor
    # [업종 소속][동종업계 비교][업황][경기 국면][거시환경]

    # ── 메시지 히스토리 ─────────────────────────────────────────────────────
    messages: Annotated[list, add_messages]