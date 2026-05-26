import json
from html import escape
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


def render() -> None:
    if not st.session_state.last_result:
        st.info("표시할 결과가 없습니다. 먼저 검색 페이지에서 심사를 실행하세요.")
        return

    result = st.session_state.last_result
    context = result.get("context", {}) if isinstance(result, dict) else {}
    report = context.get("report") if isinstance(context, dict) else None
    steps = result.get("steps", []) if isinstance(result, dict) else []
    report_step = _find_step_output(steps, "report")
    decision_step = _find_step_output(steps, "decision")
    report_payload = report if isinstance(report, dict) else {}
    explanation = context.get("explanation", {}) if isinstance(context, dict) else {}

    decision = report_payload.get("decision") or context.get("decision") or "-"
    credit_grade = report_payload.get("credit_grade") or context.get("credit_grade") or "-"
    confidence = report_payload.get("confidence")
    if confidence is None:
        confidence = context.get("decision_confidence")
    recommended_limit = report_payload.get("recommended_limit")
    if recommended_limit is None:
        recommended_limit = context.get("recommended_limit")

    _inject_styles()

    if not report_payload:
        st.warning("최종 report 데이터가 없습니다. 하단 Raw Data에서 응답 구조를 확인하세요.")

    _render_overview_card(
        report_payload,
        context,
        result,
        decision,
        credit_grade,
        confidence,
        recommended_limit,
    )
    _render_summary_card(report_payload)
    _render_risk_recommendation_card(report_payload, context, explanation)
    _render_decision_details_card(decision_step, context)
    _render_agent_verification(report_step, decision_step, report_payload)
    _render_raw_data(result, context, steps)

    st.markdown("---")
    _render_pdf_print_button(
        report_payload,
        context,
        result,
        decision,
        credit_grade,
        confidence,
        recommended_limit,
        decision_step,
        explanation,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "JSON 다운로드",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name="credit_assessment_result.json",
            mime="application/json",
        )
    with col2:
        if st.button("다시 검색 페이지로 이동"):
            st.session_state.page = "Search"
            st.rerun()


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #f8fbff 0%, #f4f7fb 100%);
        }
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        .report-card {
            background: #ffffff;
            border: 1px solid #dbe4ef;
            border-radius: 22px;
            padding: 24px 24px 20px;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
            margin-bottom: 1rem;
        }
        .overview-card {
            background: linear-gradient(180deg, #f6fbff 0%, #eef5fb 100%);
            border: 1px solid #d7e6f4;
        }
        .card-title {
            color: #1f3552;
            font-size: 1.08rem;
            font-weight: 800;
            margin-bottom: 0.9rem;
        }
        .company-name {
            color: #172b45;
            font-size: 1.85rem;
            font-weight: 800;
            line-height: 1.15;
            margin-bottom: 0.5rem;
        }
        .company-meta {
            color: #5f6f86;
            font-size: 0.95rem;
            line-height: 1.6;
            margin-bottom: 1rem;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 7px 12px;
            font-size: 0.87rem;
            font-weight: 700;
            margin-right: 0.45rem;
            margin-bottom: 0.5rem;
        }
        .badge-approve {
            background: #e9f8ef;
            color: #1f7a4c;
            border: 1px solid #ccebd8;
        }
        .badge-review {
            background: #fff5df;
            color: #976400;
            border: 1px solid #f2dfae;
        }
        .badge-reject {
            background: #ffecee;
            color: #b23d49;
            border: 1px solid #f3c7cd;
        }
        .badge-default {
            background: #eef3f8;
            color: #526277;
            border: 1px solid #d9e3ec;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 0.5rem;
        }
        .metric-box {
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid #dbe4ef;
            border-radius: 16px;
            padding: 16px 16px 14px;
        }
        .metric-label {
            color: #66758a;
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .metric-value {
            color: #16263e;
            font-size: 1.45rem;
            font-weight: 800;
            margin-top: 0.45rem;
            line-height: 1.2;
        }
        .body-copy {
            color: #334155;
            font-size: 0.98rem;
            line-height: 1.75;
        }
        .split-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
        }
        .subsection-title {
            color: #24405f;
            font-size: 0.96rem;
            font-weight: 800;
            margin: 0 0 0.7rem 0;
        }
        .item-chip {
            border-radius: 14px;
            padding: 11px 13px;
            font-size: 0.94rem;
            line-height: 1.55;
            margin-bottom: 0.6rem;
            border: 1px solid #dbe4ef;
            background: #f9fbfd;
            color: #334155;
        }
        .item-risk {
            background: #fff6f7;
            border-color: #f2d3d7;
        }
        .item-good {
            background: #f6fcf8;
            border-color: #d2eadb;
        }
        .mini-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 1rem;
        }
        .mini-box {
            border: 1px solid #dbe4ef;
            background: #f9fbfd;
            border-radius: 16px;
            padding: 15px 16px;
        }
        .mini-label {
            color: #66758a;
            font-size: 0.8rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .mini-value {
            color: #16263e;
            font-size: 1.05rem;
            font-weight: 800;
            margin-top: 0.45rem;
            line-height: 1.35;
        }
        .inspect-box {
            border-radius: 18px;
            padding: 16px 18px;
            border: 1px solid #d6e6dd;
            background: #f4fbf6;
            color: #21543a;
            margin-top: 1rem;
        }
        .inspect-box.warn {
            border-color: #efdfb6;
            background: #fffaf0;
            color: #7b5900;
        }
        .inspect-box.danger {
            border-color: #efc9ce;
            background: #fff6f7;
            color: #8e313a;
        }
        @media (max-width: 900px) {
            .metrics-grid,
            .split-grid,
            .mini-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_overview_card(
    report: dict[str, Any],
    context: dict[str, Any],
    result: dict[str, Any],
    decision: str,
    credit_grade: str,
    confidence: Any,
    recommended_limit: Any,
) -> None:
    company_name = report.get("company_name") or context.get("company_name") or "대상 기업"
    corp_name = report.get("corp_name") or context.get("corp_name") or "-"
    corp_code = report.get("corp_code") or context.get("corp_code") or "-"
    generated_at = report.get("generated_at", "-")
    status = result.get("status", "unknown")

    st.markdown(
        f"""
        <div class="report-card overview-card">
            <div class="company-name">{company_name}</div>
            <div class="company-meta">
                법인명: {corp_name} | 법인코드: {corp_code} | 워크플로우 상태: {status} | 생성일: {generated_at}
            </div>
            <div>
                <span class="badge {_decision_badge_class(decision)}">최종 결정 {_format_decision(decision)}</span>
                <span class="badge badge-default">신용등급 {credit_grade}</span>
            </div>
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-label">최종 결정</div>
                    <div class="metric-value">{_format_decision(decision)}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">신용등급</div>
                    <div class="metric-value">{credit_grade}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">판단 신뢰도</div>
                    <div class="metric-value">{_format_confidence(confidence)}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">추천 한도</div>
                    <div class="metric-value">{_format_currency(recommended_limit)}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_summary_card(report: dict[str, Any]) -> None:
    summary = report.get("summary") or "요약 정보가 없습니다."
    st.markdown(
        f"""
        <div class="report-card">
            <div class="card-title">종합 요약</div>
            <div class="body-copy">{summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_risk_recommendation_card(
    report: dict[str, Any],
    context: dict[str, Any],
    explanation: dict[str, Any],
) -> None:
    key_risks = report.get("key_risks") or context.get("decision_reasons") or []
    recommendation = report.get("recommendation") or "권고 정보가 없습니다."
    positive_factors = explanation.get("key_positive_factors", [])
    overall_risk_level = context.get("overall_risk_level") or "-"
    critical_count = context.get("critical_count", 0)
    high_count = context.get("high_count", 0)
    medium_count = context.get("medium_count", 0)
    low_count = context.get("low_count", 0)

    risk_items = "".join(
        f'<div class="item-chip item-risk">{item}</div>' for item in key_risks
    ) or '<div class="item-chip item-risk">주요 리스크 정보가 없습니다.</div>'
    positive_items = "".join(
        f'<div class="item-chip item-good">{item}</div>' for item in positive_factors
    ) or '<div class="item-chip item-good">긍정 요인 정보가 없습니다.</div>'

    st.markdown(
        f"""
        <div class="report-card">
            <div class="card-title">리스크 및 권고</div>
            <div class="split-grid">
                <div>
                    <div class="subsection-title">주요 리스크</div>
                    {risk_items}
                </div>
                <div>
                    <div class="subsection-title">심사 권고</div>
                    <div class="body-copy">{recommendation}</div>
                </div>
                <div>
                    <div class="subsection-title">리스크 집계</div>
                    <div class="item-chip">
                        통합 리스크 수준: {overall_risk_level}<br/>
                        CRITICAL {critical_count}건 / HIGH {high_count}건 / MEDIUM {medium_count}건 / LOW {low_count}건
                    </div>
                </div>
                <div>
                    <div class="subsection-title">긍정 요인</div>
                    {positive_items}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_decision_details_card(
    decision_step: dict[str, Any] | None,
    context: dict[str, Any],
) -> None:
    reasons = context.get("decision_reasons", [])
    processing_errors = context.get("processing_errors", [])
    grade_detail = context.get("grade_detail", {})
    explanation = context.get("explanation", {})

    if decision_step:
        credit_score = decision_step.get("credit_score")
        limit_range = decision_step.get("limit_range")
        limit_basis = decision_step.get("limit_basis")
    else:
        credit_score = context.get("credit_score")
        limit_range = context.get("limit_range")
        limit_basis = context.get("limit_basis")

    breakdown = grade_detail.get("score_breakdown", {}) if isinstance(grade_detail, dict) else {}
    rationale = grade_detail.get("rationale") if isinstance(grade_detail, dict) else "-"
    key_risk_factors = explanation.get("key_risk_factors", []) if isinstance(explanation, dict) else []

    reason_items = "".join(
        f'<div class="item-chip">{item}</div>' for item in reasons
    ) or '<div class="item-chip">판단 사유 정보가 없습니다.</div>'
    factor_items = "".join(
        f'<div class="item-chip item-risk">{item}</div>' for item in key_risk_factors
    ) or '<div class="item-chip item-risk">설명 기반 리스크 요인이 없습니다.</div>'
    error_items = "".join(
        f'<div class="item-chip item-risk">{item}</div>' for item in processing_errors
    ) or '<div class="item-chip item-good">처리 중 기록된 오류가 없습니다.</div>'

    st.markdown(
        f"""
        <div class="report-card">
            <div class="card-title">판단 상세</div>
            <div class="mini-grid">
                <div class="mini-box">
                    <div class="mini-label">신용점수</div>
                    <div class="mini-value">{credit_score if credit_score is not None else '-'}</div>
                </div>
                <div class="mini-box">
                    <div class="mini-label">한도 범위</div>
                    <div class="mini-value">{limit_range or '-'}</div>
                </div>
                <div class="mini-box">
                    <div class="mini-label">기본 점수</div>
                    <div class="mini-value">{breakdown.get('base_score', '-')}</div>
                </div>
                <div class="mini-box">
                    <div class="mini-label">최종 점수</div>
                    <div class="mini-value">{breakdown.get('final_score', '-')}</div>
                </div>
                <div class="mini-box">
                    <div class="mini-label">리스크 차감</div>
                    <div class="mini-value">{breakdown.get('risk_deduction', '-')}</div>
                </div>
                <div class="mini-box">
                    <div class="mini-label">재무 차감</div>
                    <div class="mini-value">{breakdown.get('financial_deduction', '-')}</div>
                </div>
            </div>
            <div class="split-grid">
                <div>
                    <div class="subsection-title">한도 산정 근거</div>
                    <div class="item-chip">{limit_basis or '-'}</div>
                    <div class="subsection-title" style="margin-top: 1rem;">판단 사유</div>
                    {reason_items}
                </div>
                <div>
                    <div class="subsection-title">등급 산출 근거</div>
                    <div class="item-chip">{rationale}</div>
                    <div class="subsection-title" style="margin-top: 1rem;">설명 기반 리스크 요인</div>
                    {factor_items}
                    <div class="subsection-title" style="margin-top: 1rem;">처리 로그</div>
                    {error_items}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_agent_verification(
    report_step: dict[str, Any] | None,
    decision_step: dict[str, Any] | None,
    report: dict[str, Any],
) -> None:
    report_output = report_step.get("report") if isinstance(report_step, dict) else None
    if report_output and report:
        box_class = "inspect-box"
        report_message = "ReportAgent output과 최종 context.report가 모두 존재합니다."
    elif report_output:
        box_class = "inspect-box warn"
        report_message = "ReportAgent output은 있으나 최종 context.report는 비어 있습니다."
    else:
        box_class = "inspect-box danger"
        report_message = "ReportAgent output을 찾지 못했습니다."

    if decision_step:
        decision_message = "DecisionAgent output이 존재하므로 ReportAgent 입력 검증이 가능합니다."
    else:
        decision_message = "DecisionAgent output을 찾지 못했습니다."

    st.markdown(
        f"""
        <div class="{box_class}">
            <div class="card-title" style="margin-bottom: 0.45rem;">에이전트 전달 검증</div>
            <div class="body-copy">{report_message}</div>
            <div class="body-copy" style="margin-top: 0.35rem;">{decision_message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_raw_data(
    result: dict[str, Any],
    context: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    with st.expander("Raw Data 보기"):
        st.markdown("**context**")
        st.json(context)
        st.markdown("**steps**")
        st.json(steps)
        st.markdown("**원본 응답 전체**")
        st.json(result)


def _render_pdf_print_button(
    report: dict[str, Any],
    context: dict[str, Any],
    result: dict[str, Any],
    decision: str,
    credit_grade: str,
    confidence: Any,
    recommended_limit: Any,
    decision_step: dict[str, Any] | None,
    explanation: dict[str, Any],
) -> None:
    printable_html = _build_printable_html(
        report,
        context,
        result,
        decision,
        credit_grade,
        confidence,
        recommended_limit,
        decision_step,
        explanation,
    )
    encoded_html = json.dumps(printable_html)
    components.html(
        f"""
        <div style="margin: 0.25rem 0 1rem 0;">
          <button
            onclick="openPrintView()"
            style="
              background:#eef5fb;
              color:#1f3552;
              border:1px solid #d7e6f4;
              border-radius:10px;
              padding:10px 16px;
              font-size:14px;
              font-weight:600;
              cursor:pointer;
            "
          >
            PDF로 저장/인쇄
          </button>
        </div>
        <script>
          function openPrintView() {{
            const html = {encoded_html};
            const printWindow = window.open('', '_blank');
            printWindow.document.open();
            printWindow.document.write(html);
            printWindow.document.close();
            printWindow.focus();
            setTimeout(() => printWindow.print(), 300);
          }}
        </script>
        """,
        height=60,
    )


def _find_step_output(steps: list[dict[str, Any]], agent_name: str) -> dict[str, Any] | None:
    for step in steps:
        if step.get("agent_name") == agent_name:
            output = step.get("output")
            return output if isinstance(output, dict) else None
    return None


def _format_decision(decision: str) -> str:
    return {
        "approve": "승인",
        "review": "재검토",
        "reject": "거절",
    }.get(decision, str(decision))


def _decision_badge_class(decision: str) -> str:
    return {
        "approve": "badge-approve",
        "review": "badge-review",
        "reject": "badge-reject",
    }.get(decision, "badge-default")


def _format_confidence(confidence: Any) -> str:
    if confidence is None:
        return "-"
    try:
        return f"{float(confidence) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(confidence)


def _format_currency(amount: Any) -> str:
    if amount in (None, "", 0):
        return "-"
    try:
        numeric_amount = float(amount)
    except (TypeError, ValueError):
        return str(amount)

    if abs(numeric_amount) >= 100_000_000:
        return f"{numeric_amount / 100_000_000:.1f}억원"
    return f"{numeric_amount:,.0f}원"


def _build_printable_html(
    report: dict[str, Any],
    context: dict[str, Any],
    result: dict[str, Any],
    decision: str,
    credit_grade: str,
    confidence: Any,
    recommended_limit: Any,
    decision_step: dict[str, Any] | None,
    explanation: dict[str, Any],
) -> str:
    company_name = report.get("company_name") or context.get("company_name") or "대상 기업"
    corp_name = report.get("corp_name") or context.get("corp_name") or "-"
    corp_code = report.get("corp_code") or context.get("corp_code") or "-"
    generated_at = report.get("generated_at", "-")
    status = result.get("status", "unknown")
    summary = report.get("summary") or "요약 정보가 없습니다."
    recommendation = report.get("recommendation") or "권고 정보가 없습니다."
    overall_risk_level = context.get("overall_risk_level") or "-"
    critical_count = context.get("critical_count", 0)
    high_count = context.get("high_count", 0)
    medium_count = context.get("medium_count", 0)
    low_count = context.get("low_count", 0)
    reasons = context.get("decision_reasons", [])
    key_risks = report.get("key_risks") or reasons
    positive_factors = explanation.get("key_positive_factors", [])
    processing_errors = context.get("processing_errors", [])
    grade_detail = context.get("grade_detail", {})
    breakdown = grade_detail.get("score_breakdown", {}) if isinstance(grade_detail, dict) else {}
    rationale = grade_detail.get("rationale") if isinstance(grade_detail, dict) else "-"
    key_risk_factors = explanation.get("key_risk_factors", []) if isinstance(explanation, dict) else []

    if decision_step:
        credit_score = decision_step.get("credit_score")
        limit_range = decision_step.get("limit_range")
        limit_basis = decision_step.get("limit_basis")
    else:
        credit_score = context.get("credit_score")
        limit_range = context.get("limit_range")
        limit_basis = context.get("limit_basis")

    status_color = {
        "approve": "#1f7a4c",
        "review": "#976400",
        "reject": "#b23d49",
    }.get(decision, "#526277")
    status_bg = {
        "approve": "#e9f8ef",
        "review": "#fff5df",
        "reject": "#ffecee",
    }.get(decision, "#eef3f8")

    def render_list(items: list[Any]) -> str:
        if not items:
            return "<li>-</li>"
        return "".join(f"<li>{escape(str(item))}</li>" for item in items)

    return f"""
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8" />
      <title>{escape(str(company_name))} 신용평가 리포트</title>
      <style>
        @page {{
          size: A4;
          margin: 14mm;
        }}
        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          color: #1f2937;
          background: #ffffff;
          margin: 0;
        }}
        .page {{
          width: 100%;
        }}
        .card {{
          border: 1px solid #dbe4ef;
          border-radius: 18px;
          padding: 18px 20px;
          margin-bottom: 14px;
          break-inside: avoid;
        }}
        .overview {{
          background: linear-gradient(180deg, #f6fbff 0%, #eef5fb 100%);
        }}
        .title {{
          font-size: 28px;
          font-weight: 800;
          margin-bottom: 8px;
          color: #172b45;
        }}
        .meta {{
          color: #5f6f86;
          font-size: 13px;
          line-height: 1.6;
          margin-bottom: 12px;
        }}
        .badge {{
          display: inline-block;
          border-radius: 999px;
          padding: 6px 10px;
          font-size: 12px;
          font-weight: 700;
          margin-right: 6px;
          margin-bottom: 8px;
          border: 1px solid #d9e3ec;
          background: #eef3f8;
          color: #526277;
        }}
        .status {{
          background: {status_bg};
          color: {status_color};
          border-color: {status_bg};
        }}
        .metric-grid {{
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 10px;
        }}
        .metric {{
          border: 1px solid #dbe4ef;
          border-radius: 12px;
          padding: 12px;
          background: rgba(255,255,255,0.92);
        }}
        .metric-label {{
          color: #66758a;
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }}
        .metric-value {{
          color: #16263e;
          font-size: 20px;
          font-weight: 800;
          margin-top: 6px;
        }}
        .section-title {{
          color: #1f3552;
          font-size: 17px;
          font-weight: 800;
          margin-bottom: 10px;
        }}
        .body {{
          color: #334155;
          font-size: 14px;
          line-height: 1.7;
        }}
        .two-col {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 14px;
        }}
        .sub-title {{
          color: #24405f;
          font-size: 14px;
          font-weight: 800;
          margin: 0 0 8px 0;
        }}
        .box {{
          border: 1px solid #dbe4ef;
          border-radius: 12px;
          padding: 10px 12px;
          background: #f9fbfd;
          margin-bottom: 8px;
          font-size: 13px;
          line-height: 1.6;
        }}
        ul {{
          margin: 0;
          padding-left: 18px;
        }}
        li {{
          margin-bottom: 6px;
          line-height: 1.6;
          font-size: 13px;
        }}
        @media print {{
          .print-note {{
            display: none;
          }}
        }}
      </style>
    </head>
    <body>
      <div class="page">
        <div class="print-note" style="margin-bottom: 12px; color: #5f6f86; font-size: 12px;">
          브라우저 인쇄 창에서 대상 프린터를 "PDF로 저장"으로 선택하면 PDF 다운로드가 가능합니다.
        </div>
        <div class="card overview">
          <div class="title">{escape(str(company_name))}</div>
          <div class="meta">
            법인명: {escape(str(corp_name))} | 법인코드: {escape(str(corp_code))} |
            워크플로우 상태: {escape(str(status))} | 생성일: {escape(str(generated_at))}
          </div>
          <div>
            <span class="badge status">최종 결정 {escape(_format_decision(decision))}</span>
            <span class="badge">신용등급 {escape(str(credit_grade))}</span>
          </div>
          <div class="metric-grid">
            <div class="metric"><div class="metric-label">최종 결정</div><div class="metric-value">{escape(_format_decision(decision))}</div></div>
            <div class="metric"><div class="metric-label">신용등급</div><div class="metric-value">{escape(str(credit_grade))}</div></div>
            <div class="metric"><div class="metric-label">판단 신뢰도</div><div class="metric-value">{escape(_format_confidence(confidence))}</div></div>
            <div class="metric"><div class="metric-label">추천 한도</div><div class="metric-value">{escape(_format_currency(recommended_limit))}</div></div>
          </div>
        </div>

        <div class="card">
          <div class="section-title">종합 요약</div>
          <div class="body">{escape(str(summary))}</div>
        </div>

        <div class="card">
          <div class="section-title">리스크 및 권고</div>
          <div class="two-col">
            <div>
              <div class="sub-title">주요 리스크</div>
              <div class="box"><ul>{render_list(key_risks)}</ul></div>
              <div class="sub-title">리스크 집계</div>
              <div class="box">
                통합 리스크 수준: {escape(str(overall_risk_level))}<br/>
                CRITICAL {critical_count}건 / HIGH {high_count}건 / MEDIUM {medium_count}건 / LOW {low_count}건
              </div>
            </div>
            <div>
              <div class="sub-title">심사 권고</div>
              <div class="box">{escape(str(recommendation))}</div>
              <div class="sub-title">긍정 요인</div>
              <div class="box"><ul>{render_list(positive_factors)}</ul></div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="section-title">판단 상세</div>
          <div class="two-col">
            <div>
              <div class="sub-title">핵심 수치</div>
              <div class="box">신용점수: {escape(str(credit_score if credit_score is not None else '-'))}</div>
              <div class="box">한도 범위: {escape(str(limit_range or '-'))}</div>
              <div class="box">한도 산정 근거: {escape(str(limit_basis or '-'))}</div>
              <div class="sub-title">판단 사유</div>
              <div class="box"><ul>{render_list(reasons)}</ul></div>
            </div>
            <div>
              <div class="sub-title">점수 산출</div>
              <div class="box">기본 점수: {escape(str(breakdown.get('base_score', '-')))}</div>
              <div class="box">최종 점수: {escape(str(breakdown.get('final_score', '-')))}</div>
              <div class="box">리스크 차감: {escape(str(breakdown.get('risk_deduction', '-')))}</div>
              <div class="box">재무 차감: {escape(str(breakdown.get('financial_deduction', '-')))}</div>
              <div class="box">등급 산출 근거: {escape(str(rationale))}</div>
              <div class="sub-title">설명 기반 리스크 요인</div>
              <div class="box"><ul>{render_list(key_risk_factors)}</ul></div>
              <div class="sub-title">처리 로그</div>
              <div class="box"><ul>{render_list(processing_errors)}</ul></div>
            </div>
          </div>
        </div>
      </div>
    </body>
    </html>
    """
