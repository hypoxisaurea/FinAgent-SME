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
        lambda client, trace_id, attempts, required_score_names=None: {
            "id": trace_id,
            "name": "finagent_trace_verification",
            "input": {"verification": True, "api_key": "sk-lf-sensitive"},
            "output": {
                "status": "completed",
                "validation_result": {
                    "validation_passed": True,
                    "pass_rate": 1.0,
                    "passed_checks": 18,
                    "total_checks": 18,
                    "failed_checks": [],
                },
            },
            "scores": [
                {
                    "name": "validation_pass_rate",
                    "value": 1.0,
                    "dataType": "NUMERIC",
                    "comment": "All validation checks passed.",
                },
                {
                    "name": "workflow_contract_valid",
                    "value": 1,
                    "dataType": "BOOLEAN",
                    "comment": "All validation checks passed.",
                },
                {
                    "name": "failed_check_count",
                    "value": 0.0,
                    "dataType": "NUMERIC",
                    "comment": "All validation checks passed.",
                },
            ],
            "observations": [
                {
                    "name": "finagent_trace_verification",
                    "metadata": {"authorization": "Bearer sensitive"},
                }
            ],
        },
    )
    monkeypatch.setattr(
        verify_langfuse_trace,
        "_fetch_observations_with_retry",
        lambda client, trace_id, attempts: [
            {
                "name": "finagent_trace_verification",
                "input": '{"verification": true}',
                "output": '{"status": "completed"}',
                "timeToFirstToken": 0.1,
                "metadata": {"authorization": "Bearer sensitive"},
            }
        ],
    )

    evidence = verify_langfuse_trace.verify_trace(output_path=output_path)

    assert client.flushed is True
    assert evidence["verified"] is True
    assert evidence["trace_id"] == "a" * 32
    assert evidence["trace"]["input"]["api_key"] == "[REDACTED]"
    observation = evidence["trace"]["observations"][0]
    assert observation["input"] == {"verification": True}
    assert observation["timeToFirstToken"] == 0.1
    assert observation["metadata"]["authorization"] == "[REDACTED]"
    assert set(evidence["validation_scores"]) == {
        "validation_pass_rate",
        "workflow_contract_valid",
        "failed_check_count",
    }
    saved_evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_evidence["verified"] is True
    assert saved_evidence["trace"]["output"]["status"] == "completed"
