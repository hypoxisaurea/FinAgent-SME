import time
from html import escape

import requests
import streamlit as st


STATUS_META: dict[str, dict[str, str | int]] = {
    "queued": {
        "label": "접수 완료",
        "headline": "심사 대기열에 작업이 등록되었습니다.",
        "description": "수집 파이프라인을 준비하고 첫 번째 에이전트를 깨우는 중입니다.",
        "progress": 18,
    },
    "running": {
        "label": "분석 진행 중",
        "headline": "에이전트들이 재무·리스크 신호를 읽고 있습니다.",
        "description": "기업 정보 수집, 리스크 판단, 보고서 조립을 순차적으로 진행합니다.",
        "progress": 64,
    },
    "succeeded": {
        "label": "완료 직전",
        "headline": "최종 보고서를 정리했습니다.",
        "description": "결과 화면으로 전환할 준비를 마쳤습니다.",
        "progress": 100,
    },
    "failed": {
        "label": "처리 실패",
        "headline": "심사 작업이 중단되었습니다.",
        "description": "상세 상태를 확인한 뒤 다시 시도해주세요.",
        "progress": 100,
    },
}

AGGREGATE_STEP_KEYS = {
    "total",
    "completed",
    "succeeded",
    "failed",
    "running",
    "queued",
    "pending",
}


def _render_http_error(response: requests.Response) -> None:
    status_code = response.status_code
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    st.error(f"워크플로우 호출 실패 ({status_code})")
    st.json(payload)


def run_health_check() -> dict | None:
    try:
        resp = requests.get(f"{st.session_state.base_url}/api/health", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error("Health check failed")
        st.exception(e)
        return None


def submit_workflow_job(company_name: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs"
        payload = {"company_name": company_name}
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            st.error("워크플로우 job 생성 실패")
            st.exception(e)
        return None
    except Exception as e:
        st.error("워크플로우 job 생성 실패")
        st.exception(e)
        return None


def get_workflow_job_status(job_id: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs/{job_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            st.error("워크플로우 job 상태 조회 실패")
            st.exception(e)
        return None
    except Exception as e:
        st.error("워크플로우 job 상태 조회 실패")
        st.exception(e)
        return None


def get_workflow_job_result(job_id: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs/{job_id}/result"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            st.error("워크플로우 job 결과 조회 실패")
            st.exception(e)
        return None
    except Exception as e:
        st.error("워크플로우 job 결과 조회 실패")
        st.exception(e)
        return None


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(65, 137, 230, 0.16), transparent 32%),
                radial-gradient(circle at top right, rgba(18, 163, 126, 0.14), transparent 26%),
                linear-gradient(180deg, #f5f9fc 0%, #eef3f8 100%);
        }
        .block-container {
            max-width: 1040px;
            padding-top: 2.4rem;
            padding-bottom: 3rem;
        }
        h1 {
            color: #16263d;
            letter-spacing: -0.02em;
        }
        .search-hero {
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, #0f2851 0%, #133b71 55%, #1b4f8f 100%);
            border-radius: 26px;
            padding: 30px 32px;
            color: #f8fbff;
            box-shadow: 0 22px 44px rgba(15, 40, 81, 0.18);
            margin: 0.4rem 0 1.4rem;
        }
        .search-hero::after {
            content: "";
            position: absolute;
            inset: auto -8% -42% auto;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(146, 214, 255, 0.28), transparent 70%);
        }
        .search-eyebrow {
            display: inline-flex;
            align-items: center;
            padding: 7px 12px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: #d8ebff;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .search-title {
            margin: 0.95rem 0 0.55rem;
            font-size: 2rem;
            font-weight: 800;
            line-height: 1.15;
            letter-spacing: -0.03em;
        }
        .search-copy {
            max-width: 680px;
            color: rgba(240, 247, 255, 0.82);
            font-size: 1rem;
            line-height: 1.7;
            margin-bottom: 0;
        }
        .search-note {
            margin-top: 1rem;
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
        }
        .search-note-card {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 18px;
            padding: 14px 16px;
        }
        .search-note-label {
            color: #d8ebff;
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.45rem;
        }
        .search-note-value {
            color: #ffffff;
            font-size: 0.95rem;
            font-weight: 700;
            line-height: 1.4;
        }
        .stTextInput label,
        .stButton button {
            font-weight: 700;
        }
        .stTextInput input {
            border-radius: 16px;
            border: 1px solid #cfd9e5;
            background: rgba(255, 255, 255, 0.92);
            padding-left: 0.9rem;
            height: 3rem;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }
        .stTextInput input:focus {
            border-color: #2f6ed9;
            box-shadow: 0 0 0 1px #2f6ed9;
        }
        .stButton > button {
            border-radius: 16px;
            min-height: 3rem;
            border: 0;
            background: linear-gradient(135deg, #143766 0%, #2564c9 100%);
            color: #ffffff;
            box-shadow: 0 16px 30px rgba(37, 100, 201, 0.18);
        }
        .stButton > button:hover {
            filter: brightness(1.03);
        }
        div[data-testid="column"]:last-child .stButton > button {
            background: linear-gradient(135deg, #edf4ff 0%, #dce8fb 100%);
            color: #143766;
            box-shadow: none;
            border: 1px solid #c8d7f3;
        }
        .loading-shell {
            position: relative;
            overflow: hidden;
            background: linear-gradient(145deg, #ffffff 0%, #f5f9ff 100%);
            border-radius: 28px;
            border: 1px solid #d8e4f2;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.08);
            padding: 28px 28px 24px;
            margin-top: 0.4rem;
        }
        .loading-shell::before {
            content: "";
            position: absolute;
            inset: -35% -10% auto auto;
            width: 280px;
            height: 280px;
            background: radial-gradient(circle, rgba(49, 107, 213, 0.12), transparent 70%);
            pointer-events: none;
        }
        .loading-head {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-start;
        }
        .loading-kicker {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #2a5ea8;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .loading-kicker::before {
            content: "";
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: linear-gradient(135deg, #30b878 0%, #8ae1b3 100%);
            box-shadow: 0 0 0 6px rgba(48, 184, 120, 0.12);
            animation: pulseDot 1.6s ease-in-out infinite;
        }
        .loading-title {
            color: #132847;
            font-size: 1.85rem;
            font-weight: 800;
            line-height: 1.12;
            letter-spacing: -0.03em;
            margin: 0.7rem 0 0.55rem;
        }
        .loading-copy {
            color: #5d6f85;
            font-size: 0.98rem;
            line-height: 1.7;
            margin: 0;
            max-width: 690px;
        }
        .job-chip {
            flex-shrink: 0;
            background: #eff5fd;
            border: 1px solid #d7e4f4;
            border-radius: 18px;
            padding: 12px 14px;
            min-width: 190px;
        }
        .job-chip-label {
            color: #69809a;
            font-size: 0.74rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .job-chip-value {
            color: #183253;
            font-size: 0.95rem;
            font-weight: 700;
            line-height: 1.5;
            margin-top: 0.4rem;
            word-break: break-word;
        }
        .progress-meta {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: center;
            margin-top: 1.45rem;
            margin-bottom: 0.6rem;
        }
        .progress-label {
            color: #2e4767;
            font-size: 0.92rem;
            font-weight: 800;
        }
        .progress-value {
            color: #16335b;
            font-size: 1rem;
            font-weight: 800;
        }
        .progress-rail {
            width: 100%;
            height: 14px;
            border-radius: 999px;
            background: #e8eef6;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #214f97 0%, #3e7ee8 55%, #77c6ff 100%);
            background-size: 180% 180%;
            animation: gradientShift 3.5s ease infinite;
        }
        .loading-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
            margin-top: 1.15rem;
        }
        .loading-panel {
            background: rgba(248, 251, 255, 0.9);
            border: 1px solid #dde8f4;
            border-radius: 20px;
            padding: 18px;
        }
        .loading-panel-title {
            color: #24476d;
            font-size: 0.9rem;
            font-weight: 800;
            margin-bottom: 0.85rem;
        }
        .step-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }
        .step-card {
            border-radius: 16px;
            border: 1px solid #dbe5f0;
            background: #ffffff;
            padding: 14px 15px;
        }
        .step-name {
            color: #5d728c;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.45rem;
        }
        .step-value {
            color: #19314f;
            font-size: 0.98rem;
            font-weight: 700;
            line-height: 1.45;
        }
        .step-card.status-done {
            background: #f4fbf7;
            border-color: #d0ead9;
        }
        .step-card.status-active {
            background: #f5f9ff;
            border-color: #d4e3f8;
        }
        .step-card.status-error {
            background: #fff4f5;
            border-color: #f2d2d7;
        }
        .step-card.status-waiting {
            background: #fff9ef;
            border-color: #f3e2bc;
        }
        .skeleton-stack {
            display: grid;
            gap: 12px;
        }
        .skeleton-card {
            border-radius: 18px;
            padding: 14px 15px;
            border: 1px solid #dbe5f0;
            background: linear-gradient(90deg, #eef4fb 25%, #f8fbff 37%, #eef4fb 63%);
            background-size: 400% 100%;
            animation: shimmerMove 1.9s ease infinite;
        }
        .skeleton-line {
            height: 10px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.92);
            margin-bottom: 10px;
        }
        .skeleton-line.short {
            width: 48%;
            margin-bottom: 0;
        }
        .refresh-note {
            margin-top: 1rem;
            color: #64758b;
            font-size: 0.9rem;
            line-height: 1.6;
        }
        @keyframes pulseDot {
            0%, 100% { transform: scale(1); opacity: 0.9; }
            50% { transform: scale(1.18); opacity: 1; }
        }
        @keyframes shimmerMove {
            0% { background-position: 100% 50%; }
            100% { background-position: 0 50%; }
        }
        @keyframes gradientShift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        @media (max-width: 900px) {
            .search-note,
            .loading-grid,
            .step-grid {
                grid-template-columns: 1fr;
            }
            .loading-head {
                flex-direction: column;
            }
            .job-chip {
                width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _resolve_status_meta(status: str) -> dict[str, str | int]:
    return STATUS_META.get(status, STATUS_META["running"])


def _normalize_status_value(raw_status: object) -> str:
    if not isinstance(raw_status, str):
        return "default"

    status = raw_status.lower()
    if status in {"succeeded", "success", "completed", "done", "finished"}:
        return "status-done"
    if status in {"running", "processing", "in_progress", "active"}:
        return "status-active"
    if status in {"failed", "error", "cancelled", "rejected"}:
        return "status-error"
    if status in {"queued", "pending", "waiting"}:
        return "status-waiting"
    return "default"


def _format_label(raw_key: str) -> str:
    return raw_key.replace("_", " ").strip().title()


def _summarize_step_value(value: object) -> tuple[str, str]:
    if isinstance(value, dict):
        for key in ("status", "state", "result"):
            nested_value = value.get(key)
            if isinstance(nested_value, str):
                return nested_value.replace("_", " ").title(), _normalize_status_value(
                    nested_value
                )
        return f"{len(value)}개 필드", "default"

    if isinstance(value, list):
        return f"{len(value)}개 항목", "default"

    if isinstance(value, bool):
        return ("완료" if value else "대기"), ("status-done" if value else "status-waiting")

    if isinstance(value, str):
        return value.replace("_", " ").title(), _normalize_status_value(value)

    return str(value), "default"


def _extract_step_cards(step_summary: dict[str, object]) -> list[tuple[str, str, str]]:
    cards: list[tuple[str, str, str]] = []
    for key, value in step_summary.items():
        label = _format_label(key)
        if key in AGGREGATE_STEP_KEYS and isinstance(value, int):
            cards.append((label, str(value), "default"))
            continue

        summary, tone = _summarize_step_value(value)
        cards.append((label, summary, tone))
    return cards[:6]


def _estimate_progress(status: str, step_summary: dict[str, object]) -> int:
    default_progress = int(_resolve_status_meta(status)["progress"])
    if status in {"succeeded", "failed"}:
        return default_progress

    total = step_summary.get("total")
    completed = step_summary.get("completed", step_summary.get("succeeded"))
    running = step_summary.get("running")
    if isinstance(total, int) and total > 0 and isinstance(completed, int):
        running_count = running if isinstance(running, int) else 0
        progress = int(((completed + (running_count * 0.45)) / total) * 100)
        return max(default_progress, min(progress, 94))

    detailed_cards = _extract_step_cards(step_summary)
    if not detailed_cards:
        return default_progress

    completed_count = sum(1 for _, _, tone in detailed_cards if tone == "status-done")
    active_count = sum(1 for _, _, tone in detailed_cards if tone == "status-active")
    total_count = len(detailed_cards)
    progress = int(((completed_count + (active_count * 0.45)) / total_count) * 100)
    return max(default_progress, min(progress, 94))


def _render_search_intro() -> None:
    st.markdown(
        """
        <section class="search-hero">
            <div class="search-eyebrow">FinAgent Workspace</div>
            <h2 class="search-title">기업 심사 워크플로우를 한 번에 시작하세요.</h2>
            <p class="search-copy">
                회사명을 입력하면 다중 에이전트가 신용·리스크 신호를 수집하고,
                최종 의사결정 리포트까지 자동으로 정리합니다.
            </p>
            <div class="search-note">
                <div class="search-note-card">
                    <div class="search-note-label">분석 범위</div>
                    <div class="search-note-value">재무 상태, 리스크 요인, 권고 한도</div>
                </div>
                <div class="search-note-card">
                    <div class="search-note-label">진행 방식</div>
                    <div class="search-note-value">job 기반 비동기 처리 + 2초 주기 polling</div>
                </div>
                <div class="search-note-card">
                    <div class="search-note-label">결과 산출물</div>
                    <div class="search-note-value">심사 리포트, 결정 사유, 원본 JSON</div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_step_summary(step_summary: dict[str, object]) -> None:
    step_cards = _extract_step_cards(step_summary)
    if not step_cards:
        return

    cards_markup = "".join(
        f"""
        <div class="step-card {tone}">
            <div class="step-name">{escape(label)}</div>
            <div class="step-value">{escape(value)}</div>
        </div>
        """
        for label, value, tone in step_cards
    )

    st.markdown(
        f"""
        <div class="loading-panel">
            <div class="loading-panel-title">현재 수집된 진행 정보</div>
            <div class="step-grid">{cards_markup}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_loading_skeleton() -> None:
    st.markdown(
        """
        <div class="loading-panel">
            <div class="loading-panel-title">에이전트 작업 중</div>
            <div class="skeleton-stack">
                <div class="skeleton-card">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line short"></div>
                </div>
                <div class="skeleton-card">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line short"></div>
                </div>
                <div class="skeleton-card">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line short"></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_job_progress() -> None:
    job_id = st.session_state.pending_job_id
    if not job_id:
        return

    status_payload = get_workflow_job_status(job_id)
    if status_payload is None:
        return

    st.session_state.pending_job_status = status_payload
    status = status_payload.get("status", "queued")
    company_name = status_payload.get("company_name", "-")
    step_summary = status_payload.get("step_summary") or {}

    meta = _resolve_status_meta(status)
    progress = _estimate_progress(status, step_summary)

    st.markdown(
        f"""
        <section class="loading-shell">
            <div class="loading-head">
                <div>
                    <div class="loading-kicker">{escape(str(meta["label"]))}</div>
                    <div class="loading-title">{escape(str(meta["headline"]))}</div>
                    <p class="loading-copy">{escape(str(meta["description"]))}</p>
                </div>
                <div class="job-chip">
                    <div class="job-chip-label">Active Job</div>
                    <div class="job-chip-value">{escape(company_name)}</div>
                    <div class="job-chip-value">{escape(job_id)}</div>
                </div>
            </div>
            <div class="progress-meta">
                <div class="progress-label">심사 상태: {escape(status.replace("_", " ").title())}</div>
                <div class="progress-value">{progress}%</div>
            </div>
            <div class="progress-rail">
                <div class="progress-fill" style="width: {progress}%;"></div>
            </div>
            <div class="refresh-note">
                2초 간격으로 상태를 새로 확인하고 있습니다. 결과가 준비되면 자동으로 리포트 화면으로 이동합니다.
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns(2)
    with left_col:
        _render_step_summary(step_summary)
    with right_col:
        _render_loading_skeleton()

    if status == "succeeded":
        result = get_workflow_job_result(job_id)
        if result is not None:
            st.session_state.last_result = result
            st.session_state.pending_job_id = None
            st.session_state.pending_job_status = None
            st.session_state.page = "Report"
            st.rerun()
        return

    if status == "failed":
        st.error("심사 작업이 실패했습니다. 상태 정보를 확인해주세요.")
        st.session_state.pending_job_id = None
        return

    time.sleep(2)
    st.rerun()


def render() -> None:
    _inject_styles()

    if st.session_state.pending_job_id:
        _render_job_progress()
        return

    _render_search_intro()

    col1, col2 = st.columns([3, 1])
    with col1:
        company_name = st.text_input(
            "회사명",
            key="company_name_input",
            placeholder="예: Acme Trading Co.",
        )
    with col2:
        if st.button("연결 확인", use_container_width=True):
            health = run_health_check()
            if health:
                st.success("백엔드 연결 성공")
                st.json(health)

    if st.button("심사 시작", use_container_width=True):
        if not company_name:
            st.warning("회사명을 입력하세요.")
        else:
            with st.spinner("심사 작업을 접수하고 있습니다..."):
                job = submit_workflow_job(company_name)
                if job is not None:
                    st.session_state.pending_job_id = job["job_id"]
                    st.session_state.pending_job_status = job
                    st.rerun()
