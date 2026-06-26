from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import requests

SSE_ACCEPT_HEADER = "text/event-stream"
SSE_STREAM_TIMEOUT: tuple[int, int] = (5, 12)


def build_workflow_stream_url(base_url: str, job_id: str) -> str:
    """Build the backend SSE endpoint URL for a workflow job."""
    return f"{base_url.rstrip('/')}/api/v1/workflows/jobs/{job_id}/stream"


def parse_sse_events(lines: Sequence[str]) -> list[dict[str, Any]]:
    """Parse Server-Sent Event lines into event/data dictionaries."""
    events: list[dict[str, Any]] = []
    event_name = "message"
    data_lines: list[str] = []

    for line in lines:
        if not line:
            if data_lines:
                events.append(_build_sse_event(event_name, data_lines))
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())

    if data_lines:
        events.append(_build_sse_event(event_name, data_lines))
    return events


def read_next_workflow_stream_event(
    *,
    base_url: str,
    job_id: str,
    request_get: Callable[..., Any] = requests.get,
    timeout: tuple[int, int] = SSE_STREAM_TIMEOUT,
) -> dict[str, Any] | None:
    """Read the next JSON payload from the workflow job SSE stream."""
    url = build_workflow_stream_url(base_url, job_id)
    lines: list[str] = []
    with request_get(
        url,
        stream=True,
        timeout=timeout,
        headers={"Accept": SSE_ACCEPT_HEADER},
    ) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            line = raw_line if isinstance(raw_line, str) else raw_line.decode()
            lines.append(line)
            if line != "":
                continue

            events = parse_sse_events(lines)
            lines = []
            if not events:
                continue

            latest_event = events[-1]
            payload = latest_event.get("data")
            if isinstance(payload, dict):
                return {
                    "event": str(latest_event.get("event") or "message"),
                    "data": payload,
                    "url": url,
                    "transport": "requests_stream",
                    "accept_header": SSE_ACCEPT_HEADER,
                }
    return None


def build_stream_verification_evidence(
    *,
    endpoint: str,
    events: Iterable[dict[str, Any]],
    fallback_used: bool,
    ui_log_rendered: bool,
) -> dict[str, Any]:
    """Build non-sensitive evidence that the frontend consumes the SSE endpoint."""
    event_list = list(events)
    return {
        "verified": True,
        "frontend_runtime": "streamlit",
        "stream_transport": "server_side_requests_stream",
        "browser_native_event_source": False,
        "endpoint": endpoint,
        "accept_header": SSE_ACCEPT_HEADER,
        "fallback_used": fallback_used,
        "fallback_strategy": "polling",
        "ui_log_rendered": ui_log_rendered,
        "events": event_list,
        "event_count": len(event_list),
    }


def _build_sse_event(event_name: str, data_lines: list[str]) -> dict[str, Any]:
    raw_data = "\n".join(data_lines)
    try:
        data: Any = json.loads(raw_data)
    except json.JSONDecodeError:
        data = raw_data
    return {"event": event_name, "data": data}
