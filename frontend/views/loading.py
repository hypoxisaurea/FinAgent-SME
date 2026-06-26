from html import escape

import streamlit as st

try:
    from views import search
except ModuleNotFoundError:  # pragma: no cover - package import fallback for tests
    from frontend.views import search


STATUS_META: dict[str, dict[str, str]] = {
    "submitting": {
        "label": "접수 중",
        "headline": "심사 작업을 생성하고 있습니다.",
        "description": "입력한 기업 정보를 확인한 뒤 분석용 job을 등록하는 중입니다.",
    },
    "queued": {
        "label": "접수 완료",
        "headline": "심사 대기열에 작업이 등록되었습니다.",
        "description": "수집 파이프라인을 준비하고 첫 번째 에이전트를 깨우는 중입니다.",
    },
    "running": {
        "label": "분석 진행 중",
        "headline": "에이전트들이 재무·리스크 신호를 읽고 있습니다.",
        "description": "기업 정보 수집, 리스크 판단, 보고서 조립을 순차적으로 진행합니다.",
    },
    "succeeded": {
        "label": "완료 직전",
        "headline": "최종 보고서를 정리했습니다.",
        "description": "결과 화면으로 전환할 준비를 마쳤습니다.",
    },
    "failed": {
        "label": "처리 실패",
        "headline": "심사 작업이 중단되었습니다.",
        "description": "상세 상태를 확인한 뒤 다시 시도해주세요.",
    },
}

QUEUE_STALL_WARNING_INTERVAL = 5
COMPANY_NOT_FOUND_ERROR_KEY = "_loading_company_not_found_error"
RETRY_QUERY_PARAM = "retry_search"
LOADING_PHASES = (
    "기업 정보를 확인하고 있습니다.",
    "재무 및 산업 데이터를 분석하고 있습니다.",
    "비금융 리스크 신호를 검토하고 있습니다.",
    "최종 리포트 초안을 정리하고 있습니다.",
)


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .app-shell-header,
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {
            display: none !important;
        }
        .stApp {
            background:
                linear-gradient(135deg, rgba(87, 216, 239, 0.42), rgba(191, 238, 255, 0.16) 42%, rgba(79, 178, 242, 0.24)),
                linear-gradient(180deg, #dff9ff 0%, #c8effb 100%);
        }
        .block-container {
            max-width: 1160px;
            padding-top: 1rem;
            padding-bottom: 3rem;
        }
        .loading-shell {
            position: relative;
            overflow: hidden;
            background: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.76);
            border-radius: 22px;
            box-shadow: 0 26px 56px rgba(17, 83, 127, 0.22);
            padding: 48px 64px 48px;
            min-height: 620px;
        }
        .loading-shell::before {
            content: "";
            position: absolute;
            top: -18%;
            right: -22%;
            width: 72%;
            height: 134%;
            border-radius: 50%;
            background: linear-gradient(135deg, rgba(138, 235, 246, 0.96) 0%, rgba(108, 210, 244, 0.92) 52%, rgba(83, 177, 235, 0.9) 100%);
            pointer-events: none;
        }
        .loading-shell::after {
            content: "";
            position: absolute;
            right: 7%;
            top: 19%;
            width: 26%;
            height: 38%;
            border-radius: 28px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.35), rgba(255, 255, 255, 0.12));
            border: 1px solid rgba(255, 255, 255, 0.34);
            transform: rotate(-7deg);
            pointer-events: none;
        }
        .loading-head {
            position: relative;
            z-index: 1;
            display: flex;
            justify-content: space-between;
            gap: 44px;
            align-items: flex-start;
        }
        .loading-kicker {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #736cff;
            font-size: 1rem;
            font-weight: 800;
            margin-top: 1.6rem;
        }
        .loading-kicker::before {
            content: "";
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #736cff;
            box-shadow: 0 0 0 7px rgba(115, 108, 255, 0.12);
            animation: pulseDot 1.6s ease-in-out infinite;
        }
        .loading-title {
            max-width: 680px;
            color: #736cff;
            font-size: 2.28rem;
            font-weight: 800;
            line-height: 1.22;
            letter-spacing: 0;
            margin: 2rem 0 1rem;
        }
        .loading-copy {
            max-width: 560px;
            color: #263445;
            font-size: 1.02rem;
            font-weight: 700;
            line-height: 1.7;
            margin: 0;
        }
        .loading-visual {
            position: relative;
            min-width: 300px;
            min-height: 230px;
        }
        .loading-orbit-card {
            position: absolute;
            right: 22px;
            bottom: 4px;
            width: 170px;
            padding: 18px;
            border-radius: 22px;
            background: linear-gradient(135deg, #736cff, #55b8ff);
            box-shadow: 0 22px 44px rgba(25, 86, 140, 0.18);
            transform: rotate(8deg);
        }
        .loading-orbit-dot {
            width: 42px;
            height: 42px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.9);
            margin-bottom: 16px;
            animation: pulseDot 1.6s ease-in-out infinite;
        }
        .loading-orbit-line {
            height: 10px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.72);
            margin-bottom: 10px;
        }
        .loading-orbit-line.short {
            width: 62%;
        }
        .loading-bottom {
            position: relative;
            z-index: 1;
            max-width: 500px;
            margin-top: 8.65rem;
        }
        .progress-area {
            min-width: 0;
        }
        .progress-meta {
            position: relative;
            z-index: 1;
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: center;
            width: 100%;
            margin-bottom: 0.7rem;
        }
        .progress-label {
            color: #263445;
            font-size: 0.82rem;
            font-weight: 800;
        }
        .progress-value {
            color: #736cff;
            font-size: 0.8rem;
            font-weight: 800;
            text-align: right;
        }
        .progress-rail {
            position: relative;
            z-index: 1;
            width: 100%;
            height: 14px;
            border-radius: 999px;
            background: #e8f5ff;
            overflow: hidden;
        }
        .progress-rail::before {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.55), transparent);
            animation: shimmerRail 1.8s ease-in-out infinite;
        }
        .progress-fill {
            position: relative;
            z-index: 1;
            width: 42%;
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #55b8ff 0%, #736cff 55%, #55b8ff 100%);
            box-shadow: 0 0 18px rgba(85, 184, 255, 0.36);
            animation: indeterminateProgress 1.55s ease-in-out infinite;
        }
        .progress-fill.complete {
            width: 100%;
            background: linear-gradient(90deg, #55b8ff 0%, #736cff 100%);
            animation: none;
        }
        .progress-fill.failed {
            width: 100%;
            background: linear-gradient(90deg, #ff6b7a 0%, #d92d4c 100%);
            animation: none;
        }
        .refresh-note {
            position: relative;
            z-index: 1;
            margin-top: 1rem;
            color: #607083;
            font-size: 0.9rem;
            line-height: 1.6;
        }
        .failure-shell {
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, #fff7f8 0%, #ffffff 46%, #fff1f3 100%);
            border: 1px solid #ffd5db;
            border-radius: 22px;
            box-shadow: 0 26px 56px rgba(152, 38, 64, 0.16);
            padding: 48px 64px 48px;
            min-height: 620px;
        }
        .failure-content {
            position: relative;
            z-index: 1;
            max-width: 650px;
            margin-top: 92px;
        }
        .failure-kicker {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #d92d4c;
            font-size: 0.9rem;
            font-weight: 800;
        }
        .failure-kicker::before {
            content: "";
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #d92d4c;
            box-shadow: 0 0 0 7px rgba(217, 45, 76, 0.12);
        }
        .failure-title {
            color: #9f1239;
            font-size: 2.2rem;
            font-weight: 800;
            line-height: 1.25;
            letter-spacing: 0;
            margin: 1.6rem 0 1rem;
        }
        .failure-copy {
            color: #5f2935;
            font-size: 1rem;
            font-weight: 700;
            line-height: 1.7;
            margin: 0;
        }
        .st-key-loading-retry {
            position: relative;
            z-index: 1;
            max-width: 520px;
            margin-top: -292px;
            margin-left: 64px;
        }
        .failure-company {
            display: flex;
            align-items: center;
            box-sizing: border-box;
            height: 3.2rem;
            min-height: 3.2rem;
            max-width: 100%;
            color: #9f1239;
            background: #fff1f3;
            border: 1px solid #ffc9d2;
            border-radius: 12px;
            padding: 0 14px;
            font-size: 0.95rem;
            font-weight: 800;
            overflow-wrap: anywhere;
        }
        .st-key-loading-retry [data-testid="stHorizontalBlock"] {
            align-items: stretch;
            gap: 12px;
        }
        .st-key-loading-retry [data-testid="column"] {
            padding-left: 0 !important;
            padding-right: 0 !important;
        }
        .st-key-loading-retry [data-testid="column"] > div,
        .st-key-loading-retry [data-testid="stVerticalBlock"],
        .st-key-loading-retry [data-testid="stElementContainer"],
        .st-key-loading-retry .stMarkdown,
        .st-key-loading-retry .failure-retry-link-wrap {
            height: 3.2rem !important;
            min-height: 3.2rem !important;
        }
        .st-key-loading-retry .stMarkdown,
        .st-key-loading-retry .failure-retry-link-wrap {
            margin: 0 !important;
            display: flex;
            align-items: stretch;
        }
        .st-key-loading-retry .stMarkdown > div,
        .st-key-loading-retry .failure-retry-link-wrap > div {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        .st-key-loading-retry div[data-testid="stMarkdownContainer"] {
            display: flex;
            align-items: stretch;
            height: 3.2rem !important;
            min-height: 3.2rem !important;
        }
        .st-key-loading-retry .failure-retry-link-wrap {
            width: 100%;
        }
        .st-key-loading-retry .failure-retry-link {
            display: flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            width: 100%;
            height: 3.2rem;
            min-height: 3.2rem;
            padding: 0 1rem;
            border: 0;
            border-radius: 12px;
            background: linear-gradient(135deg, #ff6b7a 0%, #d92d4c 100%);
            color: #ffffff;
            text-decoration: none;
            font-weight: 800;
            line-height: 1;
            white-space: nowrap;
            box-shadow: 0 18px 32px rgba(217, 45, 76, 0.18);
        }
        .st-key-loading-retry .failure-retry-link:hover {
            background: linear-gradient(135deg, #f45f70 0%, #be2441 100%);
            color: #ffffff;
            text-decoration: none;
        }
        @keyframes pulseDot {
            0%, 100% { transform: scale(1); opacity: 0.9; }
            50% { transform: scale(1.18); opacity: 1; }
        }
        @keyframes indeterminateProgress {
            0% { transform: translateX(-120%); }
            52% { transform: translateX(86%); }
            100% { transform: translateX(220%); }
        }
        @keyframes shimmerRail {
            0% { transform: translateX(-100%); opacity: 0; }
            35% { opacity: 1; }
            100% { transform: translateX(100%); opacity: 0; }
        }
        @media (max-width: 900px) {
            .loading-head {
                flex-direction: column;
            }
            .loading-shell {
                padding: 34px 24px 48px;
                min-height: auto;
            }
            .loading-shell::before {
                top: auto;
                right: -18%;
                bottom: -18%;
                width: 78%;
                height: 52%;
            }
            .loading-title {
                font-size: 1.85rem;
            }
            .loading-visual {
                min-width: 100%;
                min-height: 180px;
            }
            .loading-orbit-card {
                display: none;
            }
            .loading-bottom {
                margin-top: 2.6rem;
            }
            .progress-meta {
                align-items: flex-start;
                flex-direction: column;
                gap: 8px;
            }
            .progress-value {
                text-align: left;
            }
            .failure-shell {
                padding: 34px 24px 130px;
                min-height: auto;
            }
            .failure-content {
                margin-top: 0;
            }
            .failure-title {
                font-size: 1.75rem;
            }
            .st-key-loading-retry {
                margin-top: -100px;
                margin-left: 24px;
                margin-right: 24px;
                max-width: none;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _resolve_status_meta(status: str) -> dict[str, str]:
    return STATUS_META.get(status, STATUS_META["running"])


def _resolve_progress_message(status: str) -> str:
    if status == "succeeded":
        return "분석 완료"
    if status == "failed":
        return "처리 중단"
    if status == "submitting":
        return "심사 작업을 접수하고 있습니다."

    poll_count = int(st.session_state.get(search._JOB_POLL_COUNT_KEY, 0))
    return LOADING_PHASES[poll_count % len(LOADING_PHASES)]


def _resolve_progress_fill_class(status: str) -> str:
    if status == "succeeded":
        return "progress-fill complete"
    if status == "failed":
        return "progress-fill failed"
    return "progress-fill"


def _render_loading_state(
    *,
    status: str,
) -> None:
    meta = _resolve_status_meta(status)
    progress_message = _resolve_progress_message(status)
    progress_fill_class = _resolve_progress_fill_class(status)

    st.markdown(
        f"""
        <section class="loading-shell">
            <div class="loading-head">
                <div>
                    <div class="loading-kicker">{escape(str(meta["label"]))}</div>
                    <div class="loading-title">{escape(str(meta["headline"]))}</div>
                    <p class="loading-copy">{escape(str(meta["description"]))}</p>
                </div>
                <div class="loading-visual" aria-hidden="true">
                    <div class="loading-orbit-card">
                        <div class="loading-orbit-dot"></div>
                        <div class="loading-orbit-line"></div>
                        <div class="loading-orbit-line short"></div>
                    </div>
                </div>
            </div>
            <div class="loading-bottom">
                <div class="progress-area">
                    <div class="progress-meta">
                        <div class="progress-label">심사 상태: {escape(status.replace("_", " ").title())}</div>
                        <div class="progress-value">{escape(progress_message)}</div>
                    </div>
                    <div class="progress-rail">
                        <div class="{progress_fill_class}"></div>
                    </div>
                    <div class="refresh-note">
                        분석 상태를 실시간으로 확인하고 있으며, 완료되는 즉시 결과 리포트로 이동합니다.
                    </div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _reset_pending_job_state() -> None:
    st.session_state[search._JOB_POLL_COUNT_KEY] = 0
    st.session_state[search._JOB_QUEUED_SINCE_KEY] = None
    st.session_state[search._JOB_STREAM_EVENTS_KEY] = []
    st.session_state[search._JOB_STREAM_FALLBACK_KEY] = False


def _clear_company_not_found_error() -> None:
    st.session_state[COMPANY_NOT_FOUND_ERROR_KEY] = None


def _return_to_search() -> None:
    st.session_state.last_result = None
    st.session_state.pending_job_id = None
    st.session_state.pending_job_status = None
    st.session_state.submitting_company_name = None
    _reset_pending_job_state()
    _clear_company_not_found_error()
    if "company_name_input" in st.session_state:
        st.session_state.company_name_input = ""
    st.session_state.page = "Search"
    st.rerun()


def _consume_retry_query_param() -> None:
    retry_flag = str(st.query_params.get(RETRY_QUERY_PARAM, "")).strip()
    if retry_flag != "1":
        return

    try:
        del st.query_params[RETRY_QUERY_PARAM]
    except KeyError:
        pass

    _return_to_search()


def _render_company_not_found_state() -> None:
    error_payload = st.session_state.get(COMPANY_NOT_FOUND_ERROR_KEY) or {}
    message = "입력한 회사명을 찾을 수 없습니다. 회사명을 다시 확인해주세요."
    company_name = "-"
    if isinstance(error_payload, dict):
        message = str(error_payload.get("message") or message)
        company_name = str(error_payload.get("company_name") or company_name)

    st.markdown(
        f"""
        <section class="failure-shell">
            <div class="failure-content">
                <div class="failure-kicker">조회 불가</div>
                <div class="failure-title">기업 정보를 확인할 수 없습니다.</div>
                <p class="failure-copy">{escape(message)}</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=False, key="loading-retry"):
        company_col, button_col = st.columns([2.1, 1])
        with company_col:
            st.markdown(
                f"""
                <div class="failure-company">조회 기업: {escape(company_name)}</div>
                """,
                unsafe_allow_html=True,
            )
        with button_col:
            st.markdown(
                f"""
                <div class="failure-retry-link-wrap">
                    <a class="failure-retry-link" href="?{RETRY_QUERY_PARAM}=1" target="_self">다시 검색하기</a>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _submit_pending_job() -> None:
    raw_company_name = st.session_state.get("submitting_company_name")
    company_name = str(raw_company_name or "").strip()
    if not company_name:
        return

    _reset_pending_job_state()
    _render_loading_state(
        status="submitting",
    )

    job = search.submit_workflow_job(company_name)
    st.session_state.submitting_company_name = None
    if job is None:
        return

    st.session_state.pending_job_id = job["job_id"]
    st.session_state.pending_job_status = job
    st.rerun()


def _handle_company_not_found(
    result: dict[str, object],
    company_name: str,
) -> bool:
    context = result.get("context", {})
    company_found = context.get("company_found", True) if isinstance(context, dict) else True
    if company_found is not False:
        return False

    message = "입력한 회사명을 찾을 수 없습니다. 회사명을 다시 확인해주세요."
    if isinstance(context, dict):
        message = str(context.get("workflow_message") or message)
    st.session_state.last_result = None
    st.session_state.pending_job_id = None
    st.session_state.pending_job_status = None
    st.session_state.submitting_company_name = None
    _reset_pending_job_state()
    st.session_state[COMPANY_NOT_FOUND_ERROR_KEY] = {
        "message": message,
        "company_name": company_name,
    }
    st.session_state.page = "Loading"
    return True


def _render_job_progress() -> None:
    raw_job_id = st.session_state.get("pending_job_id")
    job_id = str(raw_job_id or "").strip()
    if not job_id:
        return

    status_payload = search.stream_workflow_job_status(job_id)
    if status_payload is None:
        status_payload = search.get_workflow_job_status(job_id)
    if status_payload is None:
        return

    st.session_state.pending_job_status = status_payload
    status = str(status_payload.get("status") or "queued")
    company_name = str(status_payload.get("company_name") or "-")
    search._console_log_job_status(status_payload)

    if status == "queued":
        queued_since = st.session_state.get(search._JOB_QUEUED_SINCE_KEY)
        if queued_since is None:
            queued_since = search._utc_timestamp()
            st.session_state[search._JOB_QUEUED_SINCE_KEY] = queued_since

        poll_count = int(st.session_state.get(search._JOB_POLL_COUNT_KEY, 0))
        if (
            poll_count >= QUEUE_STALL_WARNING_INTERVAL
            and poll_count % QUEUE_STALL_WARNING_INTERVAL == 0
        ):
            health_payload = search.get_backend_health()
            search._emit_browser_console(
                level="warning",
                event="workflow_job_queue_stalled",
                payload={
                    "job_id": job_id,
                    "poll_count": poll_count,
                    "queued_since": queued_since,
                    "message": "job status가 queued에서 진행되지 않고 있습니다.",
                    "status_payload": status_payload,
                    "backend_health": health_payload,
                },
                dedupe_key=f"workflow_job_queue_stalled:{job_id}:{poll_count}",
            )
            st.warning(
                "심사 작업이 예상보다 오래 대기 중입니다. 잠시만 기다려주세요."
            )
    else:
        st.session_state[search._JOB_QUEUED_SINCE_KEY] = None

    _render_loading_state(
        status=status,
    )
    search._render_browser_console_bridge()

    if status == "succeeded":
        result = search.get_workflow_job_result(job_id)
        if result is not None:
            if _handle_company_not_found(result, company_name):
                st.rerun()
                return

            st.session_state.last_result = result
            st.session_state.pending_job_id = None
            st.session_state.pending_job_status = None
            st.session_state.submitting_company_name = None
            _reset_pending_job_state()
            st.session_state.page = "Report"
            st.rerun()
        return

    if status == "failed":
        st.error(
            str(
                status_payload.get("message")
                or "심사 작업이 실패했습니다. 잠시 후 다시 시도해주세요."
            )
        )
        if status_payload.get("error_code"):
            st.caption(f"오류 코드: {status_payload['error_code']}")
        st.session_state.pending_job_id = None
        st.session_state.pending_job_status = None
        _reset_pending_job_state()
        return

    search.time.sleep(2)
    st.rerun()


def render() -> None:
    """Render workflow submission and progress loading states."""
    _inject_styles()
    search._render_browser_console_bridge()
    _consume_retry_query_param()

    if st.session_state.get(COMPANY_NOT_FOUND_ERROR_KEY):
        _render_company_not_found_state()
        return

    if st.session_state.get("submitting_company_name"):
        _submit_pending_job()
        return

    if st.session_state.get("pending_job_id"):
        _render_job_progress()
        return

    st.session_state.page = "Search"
    st.rerun()
