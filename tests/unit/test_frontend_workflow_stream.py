from __future__ import annotations

from frontend.scripts.verify_workflow_stream import verify_frontend_sse_stream
from frontend.services.workflow_stream import (
    build_stream_verification_evidence,
    build_workflow_stream_url,
    parse_sse_events,
    read_next_workflow_stream_event,
)


class _FakeStreamResponse:
    status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, *, decode_unicode: bool):
        yield "event: progress"
        yield (
            'data: {"job_id": "job-123", "status": "running", '
            '"step_summary": {"completed": 2, "success": 2, "failed": 0}}'
        )
        yield ""


def test_parse_sse_events_handles_json_and_comments() -> None:
    events = parse_sse_events(
        [
            ": keep-alive",
            "event: progress",
            'data: {"status": "running"}',
            "",
        ]
    )

    assert events == [{"event": "progress", "data": {"status": "running"}}]


def test_read_next_workflow_stream_event_uses_sse_contract() -> None:
    observed_request: dict[str, object] = {}

    def fake_get(url: str, **kwargs):
        observed_request.update({"url": url, **kwargs})
        return _FakeStreamResponse()

    event = read_next_workflow_stream_event(
        base_url="http://backend.test/",
        job_id="job-123",
        request_get=fake_get,
    )

    assert observed_request["url"] == (
        "http://backend.test/api/v1/workflows/jobs/job-123/stream"
    )
    assert observed_request["stream"] is True
    assert observed_request["headers"] == {"Accept": "text/event-stream"}
    assert event is not None
    assert event["event"] == "progress"
    assert event["transport"] == "requests_stream"
    assert event["data"]["status"] == "running"


def test_build_stream_verification_evidence_documents_streamlit_transport() -> None:
    evidence = build_stream_verification_evidence(
        endpoint=build_workflow_stream_url("http://backend.test", "job-123"),
        events=[{"event": "progress", "status": "running"}],
        fallback_used=False,
        ui_log_rendered=True,
    )

    assert evidence["frontend_runtime"] == "streamlit"
    assert evidence["stream_transport"] == "server_side_requests_stream"
    assert evidence["browser_native_event_source"] is False
    assert evidence["fallback_strategy"] == "polling"
    assert evidence["ui_log_rendered"] is True
    assert evidence["event_count"] == 1


def test_verify_frontend_sse_stream_writes_evidence(tmp_path) -> None:
    output_path = tmp_path / "frontend_sse_stream_verification.json"

    evidence = verify_frontend_sse_stream(output_path=output_path)

    assert output_path.exists()
    assert evidence["verified"] is True
    assert evidence["request"]["stream"] is True
    assert evidence["request"]["headers"] == {"Accept": "text/event-stream"}
    assert evidence["ui_log"]["label"] == "SSE 실시간 진행 로그"
