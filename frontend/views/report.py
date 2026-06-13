import json
from html import escape
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from views.report_view_model import build_report_view_model


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

    if not report_payload:
        st.warning("최종 report 데이터가 없습니다. 하단 Raw Data에서 응답 구조를 확인하세요.")

    view_model = build_report_view_model(result, context, report_payload, decision_step)
    overview = view_model["overview"]
    sections = view_model["sections"]

    _inject_styles()
    _render_overview_card(overview)
    _render_table_section(sections["company"])
    _render_financial_health_section(sections["financial_health"])
    _render_growth_trend_section(sections["growth_trend"])
    _render_default_risk_section(sections["default_risk"])
    _render_decision_rationale_section(sections["decision_rationale"])
    _render_monitoring_section(sections["monitoring"])
    _render_agent_verification(report_step, decision_step, report_payload)

    st.markdown("---")
    _render_pdf_print_button(view_model)

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
            background:
                radial-gradient(circle at top left, rgba(216, 234, 248, 0.55), transparent 34%),
                linear-gradient(180deg, #f8fbff 0%, #f4f7fb 100%);
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
        .st-key-growth-trend-card {
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
        .metrics-grid.tight-values .mini-value {
            font-size: 1.02rem;
            white-space: nowrap;
        }
        .metric-box, .mini-box {
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid #dbe4ef;
            border-radius: 16px;
            padding: 16px 16px 14px;
        }
        .metric-label, .mini-label {
            color: #66758a;
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .metric-value, .mini-value {
            color: #16263e;
            font-size: 1.25rem;
            font-weight: 800;
            margin-top: 0.45rem;
            line-height: 1.25;
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
        .table-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }
        .table-row {
            display: flex;
            gap: 12px;
            padding: 12px 14px;
            border: 1px solid #dbe4ef;
            border-radius: 14px;
            background: #f9fbfd;
        }
        .table-label {
            width: 96px;
            flex-shrink: 0;
            color: #627287;
            font-size: 0.88rem;
            font-weight: 700;
        }
        .table-value {
            color: #1f2937;
            font-size: 0.93rem;
            line-height: 1.55;
            word-break: break-word;
        }
        .history-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 0.75rem;
            font-size: 0.9rem;
        }
        .history-table th,
        .history-table td {
            border: 1px solid #dbe4ef;
            padding: 10px 12px;
            text-align: left;
        }
        .history-table th {
            background: #f9fbfd;
            color: #627287;
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
            .table-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_overview_card(overview: dict[str, Any]) -> None:
    key_reasons = _render_chip_list(overview.get("key_reasons"), "item-chip item-risk")
    st.markdown(
        f"""
        <div class="report-card overview-card">
            <div class="company-name">{escape(str(overview["company_name"]))}</div>
            <div class="company-meta">
                법인명: {escape(str(overview["corp_name"]))} | 법인코드: {escape(str(overview["corp_code"]))} |
                종목코드: {escape(str(overview["stock_code"]))} | 워크플로우 상태: {escape(str(overview["workflow_status"]))} |
                생성일: {escape(str(overview["generated_at"]))}
            </div>
            <div>
                <span class="badge {_decision_badge_class(str(overview['decision']))}">최종 결정 {_format_decision(str(overview["decision"]))}</span>
                <span class="badge badge-default">신용등급 {escape(str(overview["credit_grade"]))}</span>
                <span class="badge badge-default">통합 리스크 {escape(str(overview["overall_risk_level"]))}</span>
            </div>
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-label">최종 결정</div>
                    <div class="metric-value">{_format_decision(str(overview["decision"]))}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">신용등급</div>
                    <div class="metric-value">{escape(str(overview["credit_grade"]))}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">판단 신뢰도</div>
                    <div class="metric-value">{escape(str(overview["confidence"]))}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-label">추천 한도</div>
                    <div class="metric-value">{escape(str(overview["recommended_limit"]))}</div>
                </div>
            </div>
            <div class="subsection-title" style="margin-top: 1rem;">핵심 리스크 및 판단 근거</div>
            {key_reasons}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_table_section(section: dict[str, Any]) -> None:
    rows = "".join(
        f"""
        <div class="table-row">
            <div class="table-label">{escape(str(label))}</div>
            <div class="table-value">{escape(str(value))}</div>
        </div>
        """
        for label, value in section.get("rows", [])
    )
    st.markdown(
        f"""
        <div class="report-card">
            <div class="card-title">{escape(str(section["title"]))}</div>
            <div class="table-grid">{rows}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_financial_health_section(section: dict[str, Any]) -> None:
    metrics = "".join(
        f"""
        <div class="mini-box">
            <div class="mini-label">{escape(str(label))}</div>
            <div class="mini-value">{escape(str(value))}</div>
        </div>
        """
        for label, value in section.get("metrics", [])
    )
    st.markdown(
        f"""
        <div class="report-card">
            <div class="card-title">{escape(str(section["title"]))}</div>
            <div class="subsection-title">핵심 지표</div>
            <div class="metrics-grid tight-values">{metrics}</div>
            <div class="subsection-title" style="margin-top: 1rem;">해석</div>
            <div class="item-chip">{escape(str(section.get("interpretation") or "-"))}</div>
            <div class="subsection-title" style="margin-top: 1rem;">신용영향</div>
            <div class="item-chip">{escape(str(section.get("credit_impact") or "-"))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_growth_trend_section(section: dict[str, Any]) -> None:
    rows = section.get("history_rows") or []
    with st.container(border=False, key="growth-trend-card"):
        st.markdown(
            f'<div class="card-title">{escape(str(section["title"]))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="subsection-title">최근 추세 해석</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="item-chip">{escape(str(section.get("recent_trend") or "-"))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="subsection-title" style="margin-top: 1rem;">성장 둔화 및 이상 플래그</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            _render_chip_list(section.get("financial_flags"), "item-chip item-risk"),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="subsection-title" style="margin-top: 1rem;">최근 연도 추세</div>',
            unsafe_allow_html=True,
        )
        if rows:
            st.table(
                [
                    {
                        "연도": year,
                        "매출액": revenue,
                        "당기순이익": net_income,
                        "총자산": total_assets,
                    }
                    for year, revenue, net_income, total_assets in rows
                ]
            )
        else:
            st.markdown(
                '<div class="item-chip">표시할 최근 연도 추세 데이터가 없습니다.</div>',
                unsafe_allow_html=True,
            )


def _render_default_risk_section(section: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="report-card">
            <div class="card-title">{escape(str(section["title"]))}</div>
            <div class="split-grid">
                <div>
                    <div class="subsection-title">부도위험 지표</div>
                    <div class="item-chip">Altman Z-Score: {escape(str(section["z_score"]))}</div>
                    <div class="item-chip">위험 구간: {escape(str(section["zone"]))}</div>
                    <div class="item-chip">등급 상한: {escape(str(section["grade_cap"]))}</div>
                </div>
                <div>
                    <div class="subsection-title">발동된 제한 요인</div>
                    {_render_chip_list(section.get("triggered_filters"), "item-chip item-risk")}
                    <div class="subsection-title" style="margin-top: 1rem;">세부 근거</div>
                    {_render_chip_list(section.get("filter_details"), "item-chip")}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_decision_rationale_section(section: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="report-card">
            <div class="card-title">{escape(str(section["title"]))}</div>
            <div class="subsection-title">연결 요약</div>
            <div class="item-chip">{escape(str(section.get("connected_reason") or "-"))}</div>
            <div class="split-grid" style="margin-top: 1rem;">
                <div>
                    <div class="subsection-title">최종 요약</div>
                    <div class="item-chip">{escape(str(section.get("summary") or "-"))}</div>
                    <div class="subsection-title" style="margin-top: 1rem;">판단 사유</div>
                    {_render_chip_list(section.get("reasons"), "item-chip")}
                </div>
                <div>
                    <div class="subsection-title">긍정 요인</div>
                    {_render_chip_list(section.get("positive_factors"), "item-chip item-good")}
                    <div class="subsection-title" style="margin-top: 1rem;">리스크 요인</div>
                    {_render_chip_list(section.get("risk_factors"), "item-chip item-risk")}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_monitoring_section(section: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="report-card">
            <div class="card-title">{escape(str(section["title"]))}</div>
            <div class="split-grid">
                <div>
                    <div class="subsection-title">권고안</div>
                    <div class="item-chip">{escape(str(section.get("recommendation") or "-"))}</div>
                    <div class="subsection-title" style="margin-top: 1rem;">기본 판단 조건</div>
                    <div class="item-chip">결정: {escape(str(section["decision"]))}</div>
                    <div class="item-chip">권고 한도: {escape(str(section["recommended_limit"]))}</div>
                </div>
                <div>
                    <div class="subsection-title">모니터링 포인트</div>
                    {_render_chip_list(section.get("monitoring_points"), "item-chip item-risk")}
                    <div class="subsection-title" style="margin-top: 1rem;">최근 90일 리스크 이벤트</div>
                    {_render_chip_list(section.get("recent_risk_events"), "item-chip")}
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


def _render_pdf_print_button(view_model: dict[str, Any]) -> None:
    printable_html = _build_printable_html(view_model)
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


def _build_printable_html(view_model: dict[str, Any]) -> str:
    overview = view_model["overview"]
    sections = view_model["sections"]

    def render_list(items: list[Any]) -> str:
        if not items:
            return "<li>-</li>"
        return "".join(f"<li>{escape(str(item))}</li>" for item in items)

    def render_rows(rows: list[tuple[str, Any]]) -> str:
        return "".join(
            f"<tr><th>{escape(str(label))}</th><td>{escape(str(value))}</td></tr>"
            for label, value in rows
        )

    def render_metrics(metrics: list[tuple[str, Any]]) -> str:
        return "".join(
            f"<div class='metric'><div class='label'>{escape(str(label))}</div><div class='value'>{escape(str(value))}</div></div>"
            for label, value in metrics
        )

    def render_history_rows(rows: list[tuple[str, Any, Any, Any]]) -> str:
        if not rows:
            return "<tr><td>-</td><td>-</td><td>-</td><td>-</td></tr>"
        return "".join(
            f"<tr><td>{escape(str(year))}</td><td>{escape(str(revenue))}</td><td>{escape(str(net_income))}</td><td>{escape(str(total_assets))}</td></tr>"
            for year, revenue, net_income, total_assets in rows
        )

    return f"""
    <!doctype html>
    <html lang="ko">
    <head>
      <meta charset="utf-8" />
      <title>{escape(str(overview["company_name"]))} 신용평가 리포트</title>
      <style>
        @page {{
          size: A4;
          margin: 14mm;
        }}
        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          color: #1f2937;
          margin: 0;
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
        .label {{
          color: #66758a;
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }}
        .value {{
          color: #16263e;
          font-size: 18px;
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
        .box {{
          border: 1px solid #dbe4ef;
          border-radius: 12px;
          padding: 10px 12px;
          background: #f9fbfd;
          margin-bottom: 8px;
          font-size: 13px;
          line-height: 1.6;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          font-size: 13px;
        }}
        th, td {{
          border: 1px solid #dbe4ef;
          padding: 10px 12px;
          text-align: left;
          vertical-align: top;
        }}
        th {{
          width: 110px;
          background: #f9fbfd;
          color: #627287;
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
      </style>
    </head>
    <body>
      <div class="card overview">
        <div class="title">{escape(str(overview["company_name"]))}</div>
        <div class="meta">
          법인명: {escape(str(overview["corp_name"]))} | 법인코드: {escape(str(overview["corp_code"]))} |
          종목코드: {escape(str(overview["stock_code"]))} | 상태: {escape(str(overview["workflow_status"]))} |
          생성일: {escape(str(overview["generated_at"]))}
        </div>
        <div>
          <span class="badge">최종 결정 {_format_decision(str(overview["decision"]))}</span>
          <span class="badge">신용등급 {escape(str(overview["credit_grade"]))}</span>
          <span class="badge">통합 리스크 {escape(str(overview["overall_risk_level"]))}</span>
        </div>
        <div class="metric-grid">
          <div class="metric"><div class="label">최종 결정</div><div class="value">{_format_decision(str(overview["decision"]))}</div></div>
          <div class="metric"><div class="label">신용등급</div><div class="value">{escape(str(overview["credit_grade"]))}</div></div>
          <div class="metric"><div class="label">판단 신뢰도</div><div class="value">{escape(str(overview["confidence"]))}</div></div>
          <div class="metric"><div class="label">추천 한도</div><div class="value">{escape(str(overview["recommended_limit"]))}</div></div>
        </div>
      </div>

      <div class="card">
        <div class="section-title">{escape(str(sections["company"]["title"]))}</div>
        <table>{render_rows(sections["company"].get("rows", []))}</table>
      </div>

      <div class="card">
        <div class="section-title">{escape(str(sections["financial_health"]["title"]))}</div>
        <div class="metric-grid">{render_metrics(sections["financial_health"].get("metrics", []))}</div>
        <div class="box" style="margin-top: 12px;">{escape(str(sections["financial_health"].get("interpretation") or "-"))}</div>
        <div class="box">{escape(str(sections["financial_health"].get("credit_impact") or "-"))}</div>
      </div>

      <div class="card">
        <div class="section-title">{escape(str(sections["growth_trend"]["title"]))}</div>
        <div class="box">{escape(str(sections["growth_trend"].get("recent_trend") or "-"))}</div>
        <div class="box"><ul>{render_list(sections["growth_trend"].get("financial_flags", []))}</ul></div>
        <table>
          <thead>
            <tr>
              <th>연도</th>
              <th>매출액</th>
              <th>당기순이익</th>
              <th>총자산</th>
            </tr>
          </thead>
          <tbody>{render_history_rows(sections["growth_trend"].get("history_rows", []))}</tbody>
        </table>
      </div>

      <div class="card">
        <div class="section-title">{escape(str(sections["default_risk"]["title"]))}</div>
        <div class="two-col">
          <div>
            <div class="box">Altman Z-Score: {escape(str(sections["default_risk"]["z_score"]))}</div>
            <div class="box">위험 구간: {escape(str(sections["default_risk"]["zone"]))}</div>
            <div class="box">등급 상한: {escape(str(sections["default_risk"]["grade_cap"]))}</div>
          </div>
          <div>
            <div class="box"><ul>{render_list(sections["default_risk"].get("triggered_filters", []))}</ul></div>
            <div class="box"><ul>{render_list(sections["default_risk"].get("filter_details", []))}</ul></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="section-title">{escape(str(sections["decision_rationale"]["title"]))}</div>
        <div class="box">{escape(str(sections["decision_rationale"].get("connected_reason") or "-"))}</div>
        <div class="two-col">
          <div>
            <div class="box">{escape(str(sections["decision_rationale"].get("summary") or "-"))}</div>
            <div class="box"><ul>{render_list(sections["decision_rationale"].get("reasons", []))}</ul></div>
          </div>
          <div>
            <div class="box"><ul>{render_list(sections["decision_rationale"].get("positive_factors", []))}</ul></div>
            <div class="box"><ul>{render_list(sections["decision_rationale"].get("risk_factors", []))}</ul></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="section-title">{escape(str(sections["monitoring"]["title"]))}</div>
        <div class="two-col">
          <div>
            <div class="box">{escape(str(sections["monitoring"].get("recommendation") or "-"))}</div>
            <div class="box">결정: {escape(str(sections["monitoring"]["decision"]))}</div>
            <div class="box">권고 한도: {escape(str(sections["monitoring"]["recommended_limit"]))}</div>
          </div>
          <div>
            <div class="box"><ul>{render_list(sections["monitoring"].get("monitoring_points", []))}</ul></div>
            <div class="box"><ul>{render_list(sections["monitoring"].get("recent_risk_events", []))}</ul></div>
          </div>
        </div>
      </div>
    </body>
    </html>
    """


def _find_step_output(steps: list[dict[str, Any]], agent_name: str) -> dict[str, Any] | None:
    for step in steps:
        if step.get("agent_name") == agent_name:
            output = step.get("output")
            return output if isinstance(output, dict) else None
    return None


def _render_chip_list(items: list[Any] | None, css_class: str) -> str:
    if not items:
        return f'<div class="{css_class}">표시할 정보가 없습니다.</div>'
    return "".join(
        f'<div class="{css_class}">{escape(str(item))}</div>' for item in items
    )


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
