import json
import logging
import time

import requests
import streamlit as st

try:
    from frontend.services.workflow_stream import (
        parse_sse_events,
        read_next_workflow_stream_event,
    )
except ModuleNotFoundError:  # pragma: no cover - direct Streamlit entrypoint fallback
    from services.workflow_stream import (
        parse_sse_events,
        read_next_workflow_stream_event,
    )

logger = logging.getLogger(__name__)


_BROWSER_CONSOLE_DEDUPE_KEY = "_browser_console_emitted_events"
_BROWSER_CONSOLE_QUEUE_KEY = "_browser_console_events"
_BROWSER_CONSOLE_FLUSHED_COUNT_KEY = "_browser_console_flushed_count"
_JOB_POLL_COUNT_KEY = "_pending_job_poll_count"
_JOB_QUEUED_SINCE_KEY = "_pending_job_queued_since"
_JOB_STREAM_EVENTS_KEY = "_pending_job_stream_events"
_JOB_STREAM_FALLBACK_KEY = "_pending_job_stream_fallback"
_SSE_TERMINAL_EVENTS = {"complete", "error"}


def _normalize_company_name(value: str) -> str:
    return str(value or "").strip()


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _emit_browser_console(
    *,
    level: str,
    event: str,
    payload: dict[str, object],
    dedupe_key: str | None = None,
) -> None:
    emitted_events = st.session_state.setdefault(_BROWSER_CONSOLE_DEDUPE_KEY, {})
    event_key = dedupe_key or f"{event}:{json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)}"
    if emitted_events.get(event_key):
        return

    emitted_events[event_key] = True
    st.session_state[_BROWSER_CONSOLE_DEDUPE_KEY] = emitted_events
    event_queue = st.session_state.setdefault(_BROWSER_CONSOLE_QUEUE_KEY, [])
    event_queue.append(
        {
            "timestamp": _utc_timestamp(),
            "level": level,
            "event": event,
            **payload,
        }
    )
    st.session_state[_BROWSER_CONSOLE_QUEUE_KEY] = event_queue[-50:]


def _render_browser_console_bridge() -> None:
    all_events = st.session_state.get(_BROWSER_CONSOLE_QUEUE_KEY) or []
    flushed_count = int(st.session_state.get(_BROWSER_CONSOLE_FLUSHED_COUNT_KEY, 0))
    events = all_events[flushed_count:]
    if not events:
        return

    encoded_events = json.dumps(events, ensure_ascii=False, sort_keys=True, default=str)
    st.html(
        f"""
        <script>
        (() => {{
          const events = {encoded_events};
          const targets = [window, window.parent, window.top];
          const prefix = "[FinAgent-SME]";

          for (const payload of events) {{
            const level = payload.level || "log";
            const message = `${{prefix}} ${{payload.event}}`;
            for (const target of targets) {{
              try {{
                const logger = target?.console ?? window.console;
                if (typeof logger[level] === "function") {{
                  logger[level](message, payload);
                }} else {{
                  logger.log(message, payload);
                }}
              }} catch (error) {{
                window.console.warn(`${{prefix}} console_bridge_failed`, error);
              }}
            }}
          }}
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )
    st.session_state[_BROWSER_CONSOLE_FLUSHED_COUNT_KEY] = len(all_events)


def _console_log_http_error(
    *,
    status_code: int,
    code: str | None,
    message: str | None,
) -> None:
    _emit_browser_console(
        level="error",
        event="workflow_api_http_error",
        payload={
            "status_code": status_code,
            "code": code,
            "message": message,
        },
    )


def _console_log_job_status(status_payload: dict[str, object]) -> None:
    job_id = str(status_payload.get("job_id") or "-")
    status = str(status_payload.get("status") or "queued")
    step_summary = status_payload.get("step_summary") or {}
    level = "info"
    if status == "failed":
        level = "error"
    elif status in {"queued", "running"}:
        level = "info"

    _emit_browser_console(
        level=level,
        event="workflow_job_status",
        payload={
            "job_id": job_id,
            "status": status,
            "company_name": status_payload.get("company_name"),
            "error_code": status_payload.get("error_code"),
            "message": status_payload.get("message"),
            "step_summary": step_summary,
        },
        dedupe_key=f"workflow_job_status:{job_id}:{status}:{json.dumps(step_summary, ensure_ascii=False, sort_keys=True, default=str)}",
    )


def _parse_sse_events(lines: list[str]) -> list[dict[str, object]]:
    return parse_sse_events(lines)


def _append_workflow_stream_event(
    *,
    job_id: str,
    event_name: str,
    payload: dict[str, object],
) -> None:
    stream_events = st.session_state.setdefault(_JOB_STREAM_EVENTS_KEY, [])
    event_key = (
        f"{job_id}:{event_name}:"
        f"{json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)}"
    )
    if stream_events and stream_events[-1].get("event_key") == event_key:
        return
    stream_events.append(
        {
            "event_key": event_key,
            "timestamp": _utc_timestamp(),
            "event": event_name,
            "status": payload.get("status"),
            "step_summary": payload.get("step_summary"),
            "message": payload.get("message"),
        }
    )
    st.session_state[_JOB_STREAM_EVENTS_KEY] = stream_events[-8:]


def stream_workflow_job_status(job_id: str) -> dict[str, object] | None:
    try:
        stream_event = read_next_workflow_stream_event(
            base_url=str(st.session_state.base_url),
            job_id=job_id,
            request_get=requests.get,
        )
        if stream_event is None:
            return None

        payload = stream_event.get("data")
        if isinstance(payload, dict):
            event_name = str(stream_event.get("event") or "message")
            _append_workflow_stream_event(
                job_id=job_id,
                event_name=event_name,
                payload=payload,
            )
            _emit_browser_console(
                level="info" if event_name != "error" else "error",
                event="workflow_job_stream_event",
                payload={
                    "job_id": job_id,
                    "sse_event": event_name,
                    "response": payload,
                    "transport": stream_event.get("transport"),
                },
                dedupe_key=f"workflow_job_stream_event:{job_id}:{event_name}:{payload.get('status')}:{json.dumps(payload.get('step_summary'), ensure_ascii=False, sort_keys=True, default=str)}",
            )
            return payload
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        logger.info(
            "workflow_job_stream_http_failed job_id=%s error=%s",
            job_id,
            exc,
        )
    except requests.RequestException as exc:
        logger.info(
            "workflow_job_stream_transport_failed job_id=%s error=%s",
            job_id,
            exc,
        )
    st.session_state[_JOB_STREAM_FALLBACK_KEY] = True
    return None


def _render_http_error(response: requests.Response) -> None:
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    code = payload.get("code") if isinstance(payload, dict) else None
    message = payload.get("message") if isinstance(payload, dict) else None
    _console_log_http_error(
        status_code=response.status_code,
        code=code if isinstance(code, str) else None,
        message=message if isinstance(message, str) else None,
    )
    st.error(message or "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
    if code:
        st.caption(f"오류 코드: {code}")


def _render_transport_error(
    *,
    user_message: str,
    log_message: str,
    exc: Exception,
) -> None:
    logger.exception("%s error=%s", log_message, exc)
    _emit_browser_console(
        level="error",
        event=log_message,
        payload={
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "user_message": user_message,
        },
    )
    st.error(user_message)


def submit_workflow_job(company_name: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs"
        normalized_company_name = _normalize_company_name(company_name)
        payload = {"company_name": normalized_company_name}
        started_at = time.perf_counter()
        _emit_browser_console(
            level="info",
            event="workflow_job_submit_requested",
            payload={
                "company_name": normalized_company_name,
                "payload": payload,
                "url": url,
            },
        )
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        job_payload = resp.json()
        _emit_browser_console(
            level="info",
            event="workflow_job_submit_succeeded",
            payload={
                "company_name": normalized_company_name,
                "job_id": job_payload.get("job_id"),
                "status": job_payload.get("status"),
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
                "response": job_payload,
            },
            dedupe_key=f"workflow_job_submit_succeeded:{job_payload.get('job_id')}",
        )
        return job_payload
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            _render_transport_error(
                user_message="워크플로우 job 생성 중 통신 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                log_message="workflow_job_submit_transport_failed",
                exc=e,
            )
        return None
    except Exception as e:
        _render_transport_error(
            user_message="워크플로우 job 생성 중 예상치 못한 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            log_message="workflow_job_submit_unexpected_failed",
            exc=e,
        )
        return None


def get_workflow_job_status(job_id: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs/{job_id}"
        started_at = time.perf_counter()
        poll_count = int(st.session_state.get(_JOB_POLL_COUNT_KEY, 0)) + 1
        st.session_state[_JOB_POLL_COUNT_KEY] = poll_count
        _emit_browser_console(
            level="info",
            event="workflow_job_status_requested",
            payload={
                "job_id": job_id,
                "poll_count": poll_count,
                "url": url,
            },
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        status_payload = resp.json()
        _emit_browser_console(
            level="info",
            event="workflow_job_status_received",
            payload={
                "job_id": job_id,
                "poll_count": poll_count,
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
                "response": status_payload,
            },
            dedupe_key=f"workflow_job_status_received:{job_id}:{poll_count}",
        )
        return status_payload
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            _render_transport_error(
                user_message="워크플로우 상태 조회 중 통신 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                log_message="workflow_job_status_transport_failed",
                exc=e,
            )
        return None
    except Exception as e:
        _render_transport_error(
            user_message="워크플로우 상태 조회 중 예상치 못한 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            log_message="workflow_job_status_unexpected_failed",
            exc=e,
        )
        return None


def get_workflow_job_result(job_id: str) -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/v1/workflows/jobs/{job_id}/result"
        started_at = time.perf_counter()
        _emit_browser_console(
            level="info",
            event="workflow_job_result_requested",
            payload={
                "job_id": job_id,
                "url": url,
            },
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        result_payload = resp.json()
        _emit_browser_console(
            level="info",
            event="workflow_job_result_loaded",
            payload={
                "job_id": job_id,
                "keys": sorted(result_payload.keys()) if isinstance(result_payload, dict) else [],
                "latency_ms": int((time.perf_counter() - started_at) * 1000),
                "response": result_payload,
            },
            dedupe_key=f"workflow_job_result_loaded:{job_id}",
        )
        return result_payload
    except requests.HTTPError as e:
        if e.response is not None:
            _render_http_error(e.response)
        else:
            _render_transport_error(
                user_message="워크플로우 결과 조회 중 통신 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                log_message="workflow_job_result_transport_failed",
                exc=e,
            )
        return None
    except Exception as e:
        _render_transport_error(
            user_message="워크플로우 결과 조회 중 예상치 못한 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            log_message="workflow_job_result_unexpected_failed",
            exc=e,
        )
        return None


def get_backend_health() -> dict | None:
    try:
        url = f"{st.session_state.base_url}/api/health"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        payload = resp.json()
        _emit_browser_console(
            level="info",
            event="backend_health_received",
            payload={
                "response": payload,
            },
        )
        return payload
    except Exception as e:
        _render_transport_error(
            user_message="백엔드 상태 확인 중 오류가 발생했습니다.",
            log_message="backend_health_check_failed",
            exc=e,
        )
        return None


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
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
        h1 {
            color: #16263d;
            letter-spacing: -0.02em;
        }
        .app-shell-header {
            display: none;
        }
        .st-key-landing-shell {
            position: relative;
            overflow: hidden;
            background: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.76);
            border-radius: 22px;
            padding: 48px 64px 48px;
            box-shadow: 0 26px 56px rgba(17, 83, 127, 0.22);
            min-height: 620px;
        }
        .st-key-landing-shell::before {
            content: "";
            position: absolute;
            top: -18%;
            right: -22%;
            width: 72%;
            height: 134%;
            border-radius: 50%;
            background:
                linear-gradient(135deg, rgba(138, 235, 246, 0.96) 0%, rgba(108, 210, 244, 0.92) 52%, rgba(83, 177, 235, 0.9) 100%);
            pointer-events: none;
        }
        .st-key-landing-shell::after {
            content: "";
            position: absolute;
            right: 7%;
            top: 19%;
            width: 26%;
            height: 38%;
            border-radius: 28px;
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.35), rgba(255, 255, 255, 0.12));
            border: 1px solid rgba(255, 255, 255, 0.34);
            transform: rotate(-7deg);
            pointer-events: none;
        }
        .st-key-landing-shell > div {
            position: relative;
            z-index: 1;
        }
        .landing-nav {
            position: relative;
            z-index: 2;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
            margin-bottom: 18px;
        }
        .landing-brand {
            color: #736cff;
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: 0;
        }
        .landing-menu {
            display: flex;
            align-items: center;
            gap: 34px;
            color: #0b1220;
            font-size: 0.98rem;
            font-weight: 800;
        }
        .landing-action {
            color: #0b1220;
            background: #736cff;
            border-radius: 8px;
            padding: 11px 28px;
            box-shadow: 0 14px 26px rgba(115, 108, 255, 0.24);
        }
        .search-hero {
            position: relative;
            display: grid;
            grid-template-columns: minmax(0, 0.95fr) minmax(320px, 0.8fr);
            gap: 44px;
            align-items: center;
            color: #0c1729;
            margin-top: -18px;
        }
        .search-eyebrow {
            position: relative;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            padding: 0;
            border-radius: 999px;
            background: transparent;
            border: 0;
            color: #6f68ff;
            font-size: 1.08rem;
            font-weight: 800;
            letter-spacing: 0;
            text-transform: none;
        }
        .search-title {
            position: relative;
            z-index: 1;
            max-width: 600px;
            margin: 0.8rem 0 0.45rem;
            color: #736cff;
            font-size: 3.65rem;
            font-weight: 800;
            line-height: 1.12;
            letter-spacing: 0;
        }
        .search-title span {
            display: block;
            color: #736cff;
        }
        .search-copy {
            position: relative;
            z-index: 1;
            max-width: 560px;
            color: #263445;
            font-size: 1.02rem;
            font-weight: 700;
            line-height: 1.7;
            margin: 0;
        }
        .search-assurance {
            display: none;
        }
        .search-assurance-item {
            background: rgba(244, 249, 255, 0.88);
            border: 1px solid #d9e9fb;
            border-radius: 14px;
            padding: 12px 13px;
        }
        .search-assurance-label {
            color: #736cff;
            font-size: 0.72rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0;
            margin-bottom: 0.35rem;
        }
        .search-assurance-value {
            color: #1b2d45;
            font-size: 0.86rem;
            font-weight: 700;
            line-height: 1.45;
        }
        .hero-visual {
            position: relative;
            min-height: 405px;
        }
        .visual-card {
            position: absolute;
            background: rgba(255, 255, 255, 0.86);
            border: 1px solid rgba(255, 255, 255, 0.68);
            border-radius: 22px;
            box-shadow: 0 22px 44px rgba(25, 86, 140, 0.18);
            backdrop-filter: blur(12px);
        }
        .visual-card.main {
            right: 4%;
            top: 19%;
            width: 330px;
            padding: 22px;
        }
        .visual-card.floating {
            left: 5%;
            top: 10%;
            width: 112px;
            height: 96px;
            display: grid;
            place-items: center;
            color: #ffffff;
            background: linear-gradient(135deg, #736cff, #4fa8ff);
            transform: rotate(9deg);
        }
        .visual-card.score {
            left: 0;
            bottom: 17%;
            width: 152px;
            padding: 16px;
            transform: rotate(-9deg);
        }
        .visual-card.check {
            right: 0;
            top: 4%;
            width: 86px;
            height: 86px;
            display: grid;
            place-items: center;
            color: #2c8edb;
        }
        .visual-title {
            color: #0b2f5f;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            margin-bottom: 16px;
        }
        .visual-line {
            height: 10px;
            border-radius: 999px;
            background: #d8efff;
            margin-bottom: 11px;
        }
        .visual-line:nth-child(2) {
            width: 76%;
            background: linear-gradient(90deg, #5db7ff, #736cff);
        }
        .visual-line:nth-child(3) {
            width: 92%;
        }
        .visual-line:nth-child(4) {
            width: 58%;
        }
        .visual-chart {
            display: flex;
            align-items: end;
            gap: 10px;
            height: 118px;
            margin-top: 20px;
        }
        .visual-bar {
            flex: 1;
            border-radius: 12px 12px 4px 4px;
            background: linear-gradient(180deg, #43b4ff, #6f68ff);
        }
        .visual-bar:nth-child(1) { height: 42%; }
        .visual-bar:nth-child(2) { height: 68%; }
        .visual-bar:nth-child(3) { height: 52%; }
        .visual-bar:nth-child(4) { height: 88%; }
        .visual-score-label {
            color: #64748b;
            font-size: 0.74rem;
            font-weight: 800;
            text-transform: uppercase;
        }
        .visual-score-value {
            color: #0b2f5f;
            font-size: 2rem;
            font-weight: 800;
            margin-top: 4px;
        }
        .review-panel,
        .st-key-review-panel {
            position: relative;
            overflow: hidden;
            max-width: 610px;
            background: transparent;
            border: 0;
            border-radius: 0;
            padding: 0;
            box-shadow: none;
            width: 100%;
            margin-top: -31px;
            margin-bottom: 0;
        }
        .st-key-review-panel::before {
            display: none;
        }
        .st-key-review-panel > div {
            position: relative;
            width: 100%;
            z-index: 1;
        }
        .st-key-review-panel div[data-testid="stHorizontalBlock"] {
            align-items: end;
            gap: 10px;
            background: transparent;
            border-radius: 12px;
            padding: 0;
            max-width: 500px;
        }
        .st-key-review-panel div[data-testid="stForm"] {
            border: 0 !important;
            background: transparent !important;
            padding: 0 !important;
        }
        .st-key-review-panel div[data-testid="stForm"] > form {
            border: 0 !important;
            background: transparent !important;
            padding: 0 !important;
        }
        .st-key-review-panel div[data-testid="column"]:first-child {
            padding-right: 0;
        }
        .st-key-review-panel div[data-testid="column"]:last-child {
            padding-left: 0;
        }
        .review-panel-title {
            display: none;
        }
        .review-panel-copy {
            display: none;
        }
        .review-panel-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 0.75rem;
        }
        .review-panel-chip {
            color: #7068ff;
            background: transparent;
            border: 0;
            border-radius: 999px;
            padding: 0;
            font-size: 0.9rem;
            font-weight: 800;
        }
        .st-key-review-panel .stTextInput,
        .st-key-review-panel .stButton {
            height: 3.55rem;
        }
        .stTextInput > div {
            margin-bottom: 0;
        }
        .st-key-review-panel .stTextInput > div,
        .st-key-review-panel .stTextInput div[data-baseweb="input"],
        .st-key-review-panel .stButton > button {
            height: 3.55rem;
        }
        .st-key-review-panel .stTextInput div[data-baseweb="input"] {
            border-color: rgba(215, 231, 243, 0.72) !important;
            box-shadow: none !important;
        }
        .st-key-review-panel .stTextInput div[data-baseweb="input"]:focus-within {
            border-color: rgba(215, 231, 243, 0.72) !important;
            box-shadow: none !important;
        }
        .stTextInput label,
        .stButton button {
            font-weight: 700;
        }
        .stTextInput input {
            border-radius: 10px;
            border: 1px solid rgba(215, 231, 243, 0.72);
            background: #fbfdff;
            padding-left: 1.15rem;
            height: 3.55rem;
            color: #19314f;
            box-shadow: none;
        }
        .stTextInput input:focus {
            border-color: rgba(215, 231, 243, 0.72) !important;
            background: #fbfdff;
            box-shadow: none !important;
            outline: none;
        }
        .stButton > button {
            border-radius: 12px;
            height: 3.55rem;
            min-height: 3.55rem;
            border: 0;
            background: linear-gradient(135deg, #55b8ff 0%, #736cff 100%);
            color: #ffffff;
            box-shadow: none;
            padding: 0 1rem;
        }
        .st-key-review-panel div[data-testid="column"]:last-child .stButton > button {
            border-radius: 12px;
        }
        .stButton > button:hover {
            background: linear-gradient(135deg, #44aefa 0%, #645cff 100%);
            color: #ffffff;
            box-shadow: none;
        }
        .loading-shell {
            position: relative;
            overflow: hidden;
            background: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.76);
            border-radius: 22px;
            box-shadow: 0 26px 56px rgba(17, 83, 127, 0.22);
            padding: 58px 64px 56px;
            min-height: 600px;
        }
        .loading-shell::before {
            content: "";
            position: absolute;
            top: -20%;
            right: -24%;
            width: 72%;
            height: 132%;
            border-radius: 50%;
            background: linear-gradient(135deg, rgba(138, 235, 246, 0.96) 0%, rgba(108, 210, 244, 0.92) 52%, rgba(83, 177, 235, 0.9) 100%);
            pointer-events: none;
        }
        .loading-shell::after {
            content: "";
            position: absolute;
            right: 9%;
            top: 18%;
            width: 24%;
            height: 34%;
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
            letter-spacing: 0;
            text-transform: none;
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
            max-width: 590px;
            color: #736cff;
            font-size: 3.15rem;
            font-weight: 800;
            line-height: 1.12;
            letter-spacing: 0;
            margin: 1.4rem 0 1rem;
        }
        .loading-copy {
            max-width: 560px;
            color: #263445;
            font-size: 1.02rem;
            font-weight: 700;
            line-height: 1.7;
            margin: 0;
        }
        .job-chip {
            position: relative;
            z-index: 1;
            flex-shrink: 0;
            background: rgba(255, 255, 255, 0.86);
            border: 1px solid rgba(255, 255, 255, 0.68);
            border-radius: 22px;
            box-shadow: 0 22px 44px rgba(25, 86, 140, 0.18);
            backdrop-filter: blur(12px);
            padding: 22px;
            min-width: 230px;
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
        .job-chip-label {
            color: #736cff;
            font-size: 0.74rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0;
        }
        .job-chip-value {
            color: #0b2f5f;
            font-size: 1.4rem;
            font-weight: 800;
            line-height: 1.5;
            margin-top: 0.4rem;
            word-break: break-word;
        }
        .progress-meta {
            position: relative;
            z-index: 1;
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: center;
            max-width: 620px;
            margin-top: 2.1rem;
            margin-bottom: 0.7rem;
        }
        .progress-label {
            color: #263445;
            font-size: 0.92rem;
            font-weight: 800;
        }
        .progress-value {
            color: #736cff;
            font-size: 1rem;
            font-weight: 800;
        }
        .progress-rail {
            position: relative;
            z-index: 1;
            max-width: 620px;
            width: 100%;
            height: 14px;
            border-radius: 999px;
            background: #e8f5ff;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #55b8ff 0%, #736cff 100%);
        }
        .loading-panel {
            position: relative;
            z-index: 1;
            max-width: 620px;
            background: rgba(244, 249, 255, 0.88);
            border: 1px solid #d9e9fb;
            border-radius: 14px;
            padding: 16px;
            margin-top: 1.4rem;
        }
        .loading-panel-title {
            color: #736cff;
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
            border-radius: 12px;
            border: 1px solid #e0eefb;
            background: #ffffff;
            padding: 14px 15px;
        }
        .step-name {
            color: #5d728c;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0;
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
        .refresh-note {
            position: relative;
            z-index: 1;
            max-width: 620px;
            margin-top: 1rem;
            color: #607083;
            font-size: 0.9rem;
            line-height: 1.6;
        }
        .stream-log {
            position: relative;
            z-index: 1;
            max-width: 620px;
            margin-top: 14px;
            border: 1px solid #d9e9fb;
            border-radius: 14px;
            background: rgba(251, 253, 255, 0.9);
            padding: 16px 18px;
        }
        .stream-log-title {
            color: #736cff;
            font-size: 0.86rem;
            font-weight: 800;
            margin-bottom: 0.75rem;
        }
        .stream-log-row {
            display: grid;
            grid-template-columns: 120px 110px minmax(0, 1fr);
            gap: 10px;
            align-items: center;
            padding: 9px 0;
            border-top: 1px solid #ecf2f8;
            color: #35506d;
            font-size: 0.86rem;
        }
        .stream-log-row:first-of-type {
            border-top: 0;
        }
        .stream-log-event {
            color: #1d5e9d;
            font-weight: 800;
            text-transform: uppercase;
        }
        .stream-log-status {
            color: #183253;
            font-weight: 800;
        }
        .stream-log-detail {
            color: #60758c;
            overflow-wrap: anywhere;
        }
        @keyframes pulseDot {
            0%, 100% { transform: scale(1); opacity: 0.9; }
            50% { transform: scale(1.18); opacity: 1; }
        }
        @media (max-width: 900px) {
            .landing-nav {
                align-items: flex-start;
                flex-direction: column;
                margin-bottom: 34px;
            }
            .landing-menu {
                flex-wrap: wrap;
                gap: 14px;
                font-size: 0.9rem;
            }
            .search-assurance,
            .step-grid {
                grid-template-columns: 1fr;
            }
            .st-key-landing-shell {
                padding: 34px 24px 48px;
                min-height: auto;
            }
            .st-key-landing-shell::before {
                top: auto;
                right: -18%;
                bottom: -18%;
                width: 78%;
                height: 52%;
                border-radius: 999px 0 0 0;
            }
            .search-hero {
                grid-template-columns: 1fr;
            }
            .hero-visual {
                min-height: 260px;
            }
            .visual-card.main {
                right: 8%;
                top: 8%;
                width: 260px;
            }
            .visual-card.floating,
            .visual-card.check,
            .visual-card.score {
                display: none;
            }
            .review-panel,
            .st-key-review-panel {
                margin-top: 0;
            }
            .search-hero,
            .review-panel,
            .st-key-review-panel,
            .loading-shell {
                padding-left: 22px;
                padding-right: 22px;
            }
            .search-title {
                font-size: 2.25rem;
            }
            .loading-head {
                flex-direction: column;
            }
            .loading-shell {
                padding: 34px 24px;
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
                font-size: 2.25rem;
            }
            .loading-visual {
                min-width: 100%;
                min-height: 180px;
            }
            .loading-orbit-card {
                display: none;
            }
            .job-chip {
                width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_search_intro() -> None:
    st.markdown(
        """
        <nav class="landing-nav">
            <div class="landing-brand">FinAgent</div>
            <div class="landing-menu">
                <span>Credit Review</span>
                <span>Risk Analysis</span>
                <span>Report</span>
            </div>
        </nav>
        <section class="search-hero">
            <div>
                <h2 class="search-title">
                    <span>빠르고 정확한</span>
                    <span>차세대 신용평가, FinAgent</span>
                </h2>
                <p class="search-copy">
                    재무, 산업, 비금융 리스크를 한 번에 분석해 <br />
                    심사 담당자가 바로 활용할 수 있는 근거 중심 리포트를 제공합니다.
                </p>
            </div>
            <div class="hero-visual" aria-hidden="true">
                <div class="visual-card floating">
                    <svg width="42" height="42" viewBox="0 0 42 42" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M21 6L25.2 16.8L36 21L25.2 25.2L21 36L16.8 25.2L6 21L16.8 16.8L21 6Z" stroke="white" stroke-width="3" stroke-linejoin="round"/>
                    </svg>
                </div>
                <div class="visual-card check">
                    <svg width="38" height="38" viewBox="0 0 38 38" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect x="7" y="7" width="24" height="24" rx="8" stroke="currentColor" stroke-width="2.5"/>
                        <path d="M14 19.5L18 23.5L25 15.5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
                <div class="visual-card main">
                    <div class="visual-title">Risk Intelligence</div>
                    <div class="visual-line"></div>
                    <div class="visual-line"></div>
                    <div class="visual-line"></div>
                    <div class="visual-chart">
                        <div class="visual-bar"></div>
                        <div class="visual-bar"></div>
                        <div class="visual-bar"></div>
                        <div class="visual-bar"></div>
                    </div>
                </div>
                <div class="visual-card score">
                    <div class="visual-score-label">Credit Score</div>
                    <div class="visual-score-value">A-</div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render() -> None:
    _inject_styles()
    _render_browser_console_bridge()

    if st.session_state.submitting_company_name:
        st.session_state.page = "Loading"
        st.rerun()
        return

    if st.session_state.pending_job_id:
        st.session_state.page = "Loading"
        st.rerun()
        return

    with st.container(border=False, key="landing-shell"):
        _render_search_intro()

        with st.container(border=False, key="review-panel"):
            st.markdown(
                """
                <div class="review-panel-title">기업 심사 시작</div>
                <div class="review-panel-copy">
                    검토할 기업명을 입력하면 FinAgent가 심사에 필요한 데이터를 수집하고 분석을 시작합니다.
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.form("company-review-form", clear_on_submit=False):
                input_col, button_col = st.columns([2.7, 1])
                with input_col:
                    st.text_input(
                        "기업명",
                        key="company_name_input",
                        placeholder="기업명을 입력하세요",
                        label_visibility="collapsed",
                    )
                with button_col:
                    start_clicked = st.form_submit_button("심사 시작", width="stretch")

            if start_clicked:
                normalized_company_name = _normalize_company_name(
                    str(st.session_state.get("company_name_input") or "")
                )
                if not normalized_company_name:
                    st.warning("회사명을 입력하세요.")
                else:
                    st.session_state.submitting_company_name = normalized_company_name
                    st.session_state[_BROWSER_CONSOLE_DEDUPE_KEY] = {}
                    st.session_state[_BROWSER_CONSOLE_QUEUE_KEY] = []
                    st.session_state[_BROWSER_CONSOLE_FLUSHED_COUNT_KEY] = 0
                    st.session_state[_JOB_POLL_COUNT_KEY] = 0
                    st.session_state[_JOB_QUEUED_SINCE_KEY] = None
                    st.session_state[_JOB_STREAM_EVENTS_KEY] = []
                    st.session_state[_JOB_STREAM_FALLBACK_KEY] = False
                    st.session_state.page = "Loading"
                    st.rerun()
