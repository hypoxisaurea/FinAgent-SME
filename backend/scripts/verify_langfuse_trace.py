from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import signal
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.common.langfuse import get_langfuse_client, is_langfuse_enabled
from backend.common.logging import configure_logging

logger = logging.getLogger(__name__)
DEFAULT_OUTPUT_PATH = "artifacts/langfuse_trace_verification.json"


def verify_trace(
    *,
    output_path: str | Path,
    attempts: int = 5,
    flush_timeout_seconds: int = 15,
) -> dict[str, Any]:
    """테스트 trace를 전송하고 Langfuse Trace API에서 수신 여부를 확인한다."""
    if not is_langfuse_enabled():
        raise RuntimeError("Langfuse SDK 또는 자격증명이 설정되지 않았습니다.")

    client = get_langfuse_client()
    if client is None:
        raise RuntimeError("Langfuse client를 초기화할 수 없습니다.")

    with client.start_as_current_observation(
        name="finagent_trace_verification",
        as_type="chain",
        input={"verification": True},
        metadata={"feature": "observability_verification"},
    ) as observation:
        trace_id = client.get_current_trace_id() or observation.trace_id
        observation.update(output={"status": "completed"})

    _flush_with_timeout(client, timeout_seconds=flush_timeout_seconds)
    trace_payload = _fetch_trace_with_retry(trace_id, attempts=attempts)
    evidence = {
        "verified": True,
        "verified_at": datetime.now(UTC).isoformat(),
        "trace_id": trace_id,
        "trace_name": trace_payload.get("name", "finagent_trace_verification"),
        "trace_url": client.get_trace_url(trace_id=trace_id),
    }
    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "langfuse_trace_verified trace_id=%s output_path=%s",
        trace_id,
        target_path,
    )
    return evidence


def _flush_with_timeout(client: Any, *, timeout_seconds: int) -> None:
    def _handle_timeout(signum: int, frame: Any) -> None:
        raise TimeoutError("Langfuse flush가 제한 시간을 초과했습니다.")

    previous_handler = signal.signal(signal.SIGALRM, _handle_timeout)
    signal.alarm(max(timeout_seconds, 1))
    try:
        client.flush()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def _fetch_trace_with_retry(trace_id: str, *, attempts: int) -> dict[str, Any]:
    base_url = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")
    public_key = os.environ["LANGFUSE_PUBLIC_KEY"]
    secret_key = os.environ["LANGFUSE_SECRET_KEY"]
    encoded_credentials = base64.b64encode(
        f"{public_key}:{secret_key}".encode()
    ).decode()
    request = Request(
        f"{base_url}/api/public/traces/{trace_id}",
        headers={"Authorization": f"Basic {encoded_credentials}"},
    )
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            with urlopen(request, timeout=10) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 404 or attempt >= attempts:
                raise
            time.sleep(0.5 * attempt)
    raise RuntimeError("Langfuse trace 확인에 실패했습니다.")


def build_parser() -> argparse.ArgumentParser:
    """Langfuse trace 검증 CLI 파서를 생성한다."""
    parser = argparse.ArgumentParser(description="Langfuse trace 적재를 검증합니다.")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--flush-timeout-seconds", type=int, default=15)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Langfuse trace 검증 CLI 진입점."""
    configure_logging()
    args = build_parser().parse_args(argv)
    verify_trace(
        output_path=args.output_path,
        attempts=args.attempts,
        flush_timeout_seconds=args.flush_timeout_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
