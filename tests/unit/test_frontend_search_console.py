from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from frontend.views import search


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


def test_emit_browser_console_dedupes_same_event(monkeypatch) -> None:
    fake_st = SimpleNamespace(session_state={})

    monkeypatch.setattr(search, "st", fake_st)
    monkeypatch.setattr(search, "_utc_timestamp", lambda: "2026-06-19T20:30:00")

    search._emit_browser_console(
        level="info",
        event="workflow_job_status",
        payload={"job_id": "job-123", "status": "running"},
        dedupe_key="job-123:running",
    )
    search._emit_browser_console(
        level="info",
        event="workflow_job_status",
        payload={"job_id": "job-123", "status": "running"},
        dedupe_key="job-123:running",
    )

    queued_events = fake_st.session_state[search._BROWSER_CONSOLE_QUEUE_KEY]
    assert len(queued_events) == 1
    assert queued_events[0]["event"] == "workflow_job_status"
    assert queued_events[0]["job_id"] == "job-123"


def test_render_browser_console_bridge_flushes_new_events_only(monkeypatch) -> None:
    html = MagicMock()
    fake_st = SimpleNamespace(
        session_state={
            search._BROWSER_CONSOLE_QUEUE_KEY: [
                {
                    "timestamp": "2026-06-19T20:30:00",
                    "level": "info",
                    "event": "workflow_job_submit_requested",
                    "job_id": "job-123",
                }
            ],
            search._BROWSER_CONSOLE_FLUSHED_COUNT_KEY: 0,
        }
    )

    monkeypatch.setattr(search, "components", SimpleNamespace(html=html))
    monkeypatch.setattr(search, "st", fake_st)

    search._render_browser_console_bridge()
    search._render_browser_console_bridge()

    assert html.call_count == 1
    rendered_html = html.call_args.args[0]
    assert "workflow_job_submit_requested" in rendered_html
    assert "job-123" in rendered_html
    assert (
        fake_st.session_state[search._BROWSER_CONSOLE_FLUSHED_COUNT_KEY] == 1
    )


def test_render_http_error_emits_browser_console_and_ui(monkeypatch) -> None:
    error = MagicMock()
    caption = MagicMock()
    fake_st = SimpleNamespace(
        session_state={},
        error=error,
        caption=caption,
    )

    monkeypatch.setattr(search, "st", fake_st)
    monkeypatch.setattr(search, "_utc_timestamp", lambda: "2026-06-19T20:30:00")

    search._render_http_error(
        _FakeResponse(
            status_code=503,
            payload={
                "code": "workflow_backend_unavailable",
                "message": "백엔드 연결에 실패했습니다.",
            },
        )
    )

    queued_events = fake_st.session_state[search._BROWSER_CONSOLE_QUEUE_KEY]
    assert queued_events[0]["event"] == "workflow_api_http_error"
    assert queued_events[0]["code"] == "workflow_backend_unavailable"
    error.assert_called_once_with("백엔드 연결에 실패했습니다.")
    caption.assert_called_once_with("오류 코드: workflow_backend_unavailable")
