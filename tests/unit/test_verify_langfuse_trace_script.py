from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from backend.scripts import verify_langfuse_trace


class _FakeObservation:
    trace_id = "a" * 32

    def update(self, **kwargs: Any) -> None:
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.flushed = False

    @contextmanager
    def start_as_current_observation(self, **kwargs: Any):
        yield _FakeObservation()

    def get_current_trace_id(self) -> str:
        return "a" * 32

    def get_trace_url(self, *, trace_id: str) -> str:
        return f"https://langfuse.example/traces/{trace_id}"

    def flush(self) -> None:
        self.flushed = True


def test_verify_trace_flushes_and_writes_api_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    client = _FakeClient()
    output_path = tmp_path / "langfuse.json"
    monkeypatch.setattr(verify_langfuse_trace, "is_langfuse_enabled", lambda: True)
    monkeypatch.setattr(verify_langfuse_trace, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(
        verify_langfuse_trace,
        "_fetch_trace_with_retry",
        lambda trace_id, attempts: {
            "id": trace_id,
            "name": "finagent_trace_verification",
        },
    )

    evidence = verify_langfuse_trace.verify_trace(output_path=output_path)

    assert client.flushed is True
    assert evidence["verified"] is True
    assert evidence["trace_id"] == "a" * 32
    assert json.loads(output_path.read_text(encoding="utf-8"))["verified"] is True
