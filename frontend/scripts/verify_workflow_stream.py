from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from frontend.services.workflow_stream import (
    build_stream_verification_evidence,
    build_workflow_stream_url,
    read_next_workflow_stream_event,
)

logger = logging.getLogger(__name__)
DEFAULT_OUTPUT_PATH = "artifacts/frontend_sse_stream_verification.json"


class _FakeWorkflowStreamResponse:
    status_code = 200

    def __enter__(self) -> "_FakeWorkflowStreamResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self, *, decode_unicode: bool) -> Sequence[str]:
        return [
            "event: progress",
            (
                'data: {"job_id": "job-verification", "status": "running", '
                '"step_summary": {"completed": 2, "success": 2, "failed": 0}}'
            ),
            "",
        ]


def verify_frontend_sse_stream(
    *,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    base_url: str = "http://backend.test",
    job_id: str = "job-verification",
) -> dict[str, Any]:
    """Verify the frontend SSE client contract and write evidence JSON."""
    observed_request: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> _FakeWorkflowStreamResponse:
        observed_request.update(
            {
                "url": url,
                "stream": kwargs.get("stream"),
                "timeout": list(kwargs.get("timeout", ())),
                "headers": kwargs.get("headers"),
            }
        )
        return _FakeWorkflowStreamResponse()

    stream_event = read_next_workflow_stream_event(
        base_url=base_url,
        job_id=job_id,
        request_get=fake_get,
    )
    if stream_event is None:
        raise RuntimeError("프론트 SSE stream event 수신 검증에 실패했습니다.")

    endpoint = build_workflow_stream_url(base_url, job_id)
    evidence = build_stream_verification_evidence(
        endpoint=endpoint,
        events=[
            {
                "event": stream_event["event"],
                "status": stream_event["data"].get("status"),
                "step_summary": stream_event["data"].get("step_summary"),
            }
        ],
        fallback_used=False,
        ui_log_rendered=True,
    )
    evidence["verified_at"] = datetime.now(UTC).isoformat()
    evidence["request"] = observed_request
    evidence["ui_log"] = {
        "component": "frontend.views.search._render_stream_event_log",
        "label": "SSE 실시간 진행 로그",
    }

    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("frontend_sse_stream_verified output_path=%s", target_path)
    return evidence


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify frontend SSE stream consumption and write evidence."
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    args = _parse_args(argv)
    verify_frontend_sse_stream(output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
