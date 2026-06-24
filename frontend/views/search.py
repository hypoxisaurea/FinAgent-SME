import json
import logging
import time
from html import escape

import requests
import streamlit as st
import streamlit.components.v1 as components

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


STATUS_META: dict[str, dict[str, str | int]] = {
    "submitting": {
        "label": "접수 중",
        "headline": "심사 작업을 생성하고 있습니다.",
        "description": "입력한 기업 정보를 확인한 뒤 분석용 job을 등록하는 중입니다.",
        "progress": 8,
    },
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

_BROWSER_CONSOLE_DEDUPE_KEY = "_browser_console_emitted_events"
_BROWSER_CONSOLE_QUEUE_KEY = "_browser_console_events"
_BROWSER_CONSOLE_FLUSHED_COUNT_KEY = "_browser_console_flushed_count"
_JOB_POLL_COUNT_KEY = "_pending_job_poll_count"
_JOB_QUEUED_SINCE_KEY = "_pending_job_queued_since"
_JOB_STREAM_EVENTS_KEY = "_pending_job_stream_events"
_JOB_STREAM_FALLBACK_KEY = "_pending_job_stream_fallback"
_QUEUE_STALL_WARNING_INTERVAL = 5
_SSE_TERMINAL_EVENTS = {"complete", "error"}


def _normalize_company_name(value: str) -> str:
    return "".join(str(value or "").split())


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
    components.html(
        f"""
        <script>
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
        </script>
        """,
        height=1,
        width=1,
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
        .refresh-note {
            margin-top: 1rem;
            color: #64758b;
            font-size: 0.9rem;
            line-height: 1.6;
        }
        .stream-log {
            margin-top: 14px;
            border: 1px solid #dbe7f4;
            border-radius: 20px;
            background: #fbfdff;
            padding: 16px 18px;
        }
        .stream-log-title {
            color: #24476d;
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
        @keyframes gradientShift {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        @media (max-width: 900px) {
            .search-note,
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
    if status in {"submitting", "succeeded", "failed"}:
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
                    <div class="search-note-value">SSE 진행 스트림 + polling fallback</div>
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


def _render_stream_event_log() -> None:
    stream_events = st.session_state.get(_JOB_STREAM_EVENTS_KEY) or []
    if not stream_events:
        return

    rows = "".join(
        f"""
        <div class="stream-log-row">
            <div class="stream-log-event">{escape(str(event.get("event") or "-"))}</div>
            <div class="stream-log-status">{escape(str(event.get("status") or "-"))}</div>
            <div class="stream-log-detail">{escape(_summarize_stream_event(event))}</div>
        </div>
        """
        for event in stream_events[-5:]
    )
    st.markdown(
        f"""
        <div class="stream-log">
            <div class="stream-log-title">SSE 실시간 진행 로그</div>
            {rows}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _summarize_stream_event(event: dict[str, object]) -> str:
    step_summary = event.get("step_summary")
    if isinstance(step_summary, dict):
        completed = step_summary.get("completed")
        success = step_summary.get("success")
        failed = step_summary.get("failed")
        if completed is not None:
            return f"completed={completed}, success={success}, failed={failed}"
    message = event.get("message")
    if message:
        return str(message)
    return str(event.get("timestamp") or "")


def _render_loading_state(
    *,
    status: str,
    company_name: str,
    job_label: str,
    step_summary: dict[str, object] | None = None,
) -> None:
    meta = _resolve_status_meta(status)
    progress = _estimate_progress(status, step_summary or {})

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
                    <div class="job-chip-label">{escape(job_label)}</div>
                    <div class="job-chip-value">{escape(company_name)}</div>
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
                SSE 진행 스트림으로 상태를 우선 수신하고, 연결이 어려우면 2초 주기 polling으로 이어갑니다.
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if step_summary:
        _render_step_summary(step_summary)
    _render_stream_event_log()


def _submit_pending_job() -> None:
    company_name = st.session_state.submitting_company_name
    if not company_name:
        return

    st.session_state[_JOB_POLL_COUNT_KEY] = 0
    st.session_state[_JOB_QUEUED_SINCE_KEY] = None
    st.session_state[_JOB_STREAM_EVENTS_KEY] = []
    st.session_state[_JOB_STREAM_FALLBACK_KEY] = False
    _render_loading_state(
        status="submitting",
        company_name=company_name,
        job_label="Submitting",
    )

    job = submit_workflow_job(company_name)
    st.session_state.submitting_company_name = None
    if job is None:
        return

    st.session_state.pending_job_id = job["job_id"]
    st.session_state.pending_job_status = job
    st.rerun()


def _render_job_progress() -> None:
    job_id = st.session_state.pending_job_id
    if not job_id:
        return

    status_payload = stream_workflow_job_status(job_id)
    if status_payload is None:
        status_payload = get_workflow_job_status(job_id)
    if status_payload is None:
        return

    st.session_state.pending_job_status = status_payload
    status = status_payload.get("status", "queued")
    company_name = status_payload.get("company_name", "-")
    step_summary = status_payload.get("step_summary") or {}
    _console_log_job_status(status_payload)

    if status == "queued":
        queued_since = st.session_state.get(_JOB_QUEUED_SINCE_KEY)
        if queued_since is None:
            queued_since = _utc_timestamp()
            st.session_state[_JOB_QUEUED_SINCE_KEY] = queued_since

        poll_count = int(st.session_state.get(_JOB_POLL_COUNT_KEY, 0))
        if poll_count >= _QUEUE_STALL_WARNING_INTERVAL and poll_count % _QUEUE_STALL_WARNING_INTERVAL == 0:
            health_payload = get_backend_health()
            _emit_browser_console(
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
                f"작업이 아직 대기열에 머물고 있습니다. poll={poll_count}, queued_since={queued_since}"
            )
    else:
        st.session_state[_JOB_QUEUED_SINCE_KEY] = None

    _render_loading_state(
        status=status,
        company_name=company_name,
        job_label="Active Job",
        step_summary=step_summary,
    )
    _render_browser_console_bridge()

    if status == "succeeded":
        result = get_workflow_job_result(job_id)
        if result is not None:
            context = result.get("context", {}) if isinstance(result, dict) else {}
            company_found = context.get("company_found", True) if isinstance(context, dict) else True
            if company_found is False:
                message = "입력한 회사명을 찾을 수 없습니다. 회사명을 다시 확인해주세요."
                if isinstance(context, dict):
                    message = str(context.get("workflow_message") or message)
                st.error(message)
                st.session_state.last_result = None
                st.session_state.pending_job_id = None
                st.session_state.pending_job_status = None
                st.session_state.submitting_company_name = None
                st.session_state[_JOB_POLL_COUNT_KEY] = 0
                st.session_state[_JOB_QUEUED_SINCE_KEY] = None
                st.session_state[_JOB_STREAM_EVENTS_KEY] = []
                st.session_state[_JOB_STREAM_FALLBACK_KEY] = False
                st.session_state.page = "Search"
                return
            st.session_state.last_result = result
            st.session_state.pending_job_id = None
            st.session_state.pending_job_status = None
            st.session_state.submitting_company_name = None
            st.session_state[_JOB_POLL_COUNT_KEY] = 0
            st.session_state[_JOB_QUEUED_SINCE_KEY] = None
            st.session_state[_JOB_STREAM_EVENTS_KEY] = []
            st.session_state[_JOB_STREAM_FALLBACK_KEY] = False
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
        st.session_state[_JOB_POLL_COUNT_KEY] = 0
        st.session_state[_JOB_QUEUED_SINCE_KEY] = None
        st.session_state[_JOB_STREAM_EVENTS_KEY] = []
        st.session_state[_JOB_STREAM_FALLBACK_KEY] = False
        return

    time.sleep(2)
    st.rerun()


def render() -> None:
    _inject_styles()
    _render_browser_console_bridge()

    if st.session_state.submitting_company_name:
        _submit_pending_job()
        return

    if st.session_state.pending_job_id:
        _render_job_progress()
        return

    _render_search_intro()

    company_name = st.text_input(
        "회사명",
        key="company_name_input",
        placeholder="예: Acme Trading Co.",
    )

    if st.button("심사 시작", use_container_width=True):
        normalized_company_name = _normalize_company_name(company_name)
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
            st.rerun()
