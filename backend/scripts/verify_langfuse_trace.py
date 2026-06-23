from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import signal
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.agents.validation.agent import ValidationAgent
from backend.common.langfuse import get_langfuse_client, is_langfuse_enabled
from backend.common.logging import configure_logging

logger = logging.getLogger(__name__)
DEFAULT_OUTPUT_PATH = "artifacts/langfuse_trace_verification.json"
VALIDATION_SCORE_NAMES = frozenset(
    {
        "validation_pass_rate",
        "workflow_contract_valid",
        "failed_check_count",
    }
)
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "credential",
        "credentials",
        "password",
        "secret_key",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
    }
)
SENSITIVE_KEY_SUFFIXES = (
    "api_key",
    "password",
    "secret_key",
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(?:sk|pk)-lf-[a-z0-9_-]+"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
)


def verify_trace(
    *,
    output_path: str | Path,
    attempts: int = 10,
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
        with client.start_as_current_observation(
            name="langfuse_ingestion_check",
            as_type="span",
            input={"check": "trace_ingestion"},
            metadata={"verification_step": True},
        ) as verification_step:
            verification_step.update(
                output={"ingestion_event_created": True}
            )
        validation_output = asyncio.run(
            ValidationAgent().run(_build_validation_probe_payload())
        )
        observation.update(
            output={
                "status": "completed",
                "validation_result": validation_output["validation_result"],
            }
        )

    _flush_with_timeout(client, timeout_seconds=flush_timeout_seconds)
    trace_payload = _fetch_trace_with_retry(
        client,
        trace_id,
        attempts=attempts,
        required_score_names=VALIDATION_SCORE_NAMES,
    )
    trace_data = _redact_sensitive_data(_parse_json_io_fields(_to_json_data(trace_payload)))
    validation_scores = _extract_scores(trace_data, VALIDATION_SCORE_NAMES)
    missing_scores = sorted(VALIDATION_SCORE_NAMES - set(validation_scores))
    if missing_scores:
        raise RuntimeError(
            "Langfuse validation score 확인에 실패했습니다: "
            + ", ".join(missing_scores)
        )
    observations = _fetch_observations_with_retry(client, trace_id, attempts=attempts)
    trace_data["observations"] = _redact_sensitive_data(
        [
            _parse_json_io_fields(_to_json_data(observation))
            for observation in observations
        ]
    )
    evidence = {
        "verified": True,
        "verified_at": datetime.now(UTC).isoformat(),
        "trace_id": trace_id,
        "trace_name": trace_data.get("name", "finagent_trace_verification"),
        "trace_url": client.get_trace_url(trace_id=trace_id),
        "validation_scores": validation_scores,
        "trace": trace_data,
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


def _build_validation_probe_payload() -> dict[str, Any]:
    report = {
        "generated_at": "2026-06-23",
        "company_name": "Langfuse 검증기업",
        "corp_name": "Langfuse 검증기업",
        "corp_code": "00000000",
        "decision": "approve",
        "credit_grade": "A",
        "summary": "검증용 심사 보고서입니다.",
        "recommendation": "검증용 승인 권고입니다.",
        "recommended_limit": 100000000,
        "confidence": 0.9,
        "key_risks": ["검증용 리스크"],
    }
    return {
        "request_id": "req-langfuse-validation-verification",
        "company_name": "Langfuse 검증기업",
        "corp_name": "Langfuse 검증기업",
        "corp_code": "00000000",
        "decision": "approve",
        "credit_grade": "A",
        "decision_confidence": 0.9,
        "decision_reasons": ["검증용 리스크"],
        "recommended_limit": 100000000,
        "explanation": {
            "summary": report["summary"],
            "recommendation": report["recommendation"],
        },
        "report": report,
    }


def _to_json_data(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        if isinstance(payload, dict):
            return payload
    raise TypeError("Langfuse trace 응답을 JSON 객체로 변환할 수 없습니다.")


def _redact_sensitive_data(value: Any, *, key: str | None = None) -> Any:
    if key is not None:
        snake_case_key = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower().replace("-", "_")
        if snake_case_key in SENSITIVE_KEYS or snake_case_key.endswith(
            SENSITIVE_KEY_SUFFIXES
        ):
            return "[REDACTED]"
    if isinstance(value, dict):
        return {
            item_key: _redact_sensitive_data(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SENSITIVE_VALUE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value


def _parse_json_io_fields(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            item_key: _parse_json_io_fields(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_parse_json_io_fields(item) for item in value]
    if key in {"input", "output"} and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _extract_scores(
    trace_data: dict[str, Any],
    score_names: frozenset[str],
) -> dict[str, dict[str, Any]]:
    scores = trace_data.get("scores", [])
    if not isinstance(scores, list):
        return {}
    extracted: dict[str, dict[str, Any]] = {}
    for score in scores:
        if not isinstance(score, dict):
            continue
        score_name = score.get("name")
        if score_name in score_names:
            extracted[str(score_name)] = {
                key: score.get(key)
                for key in ("name", "value", "dataType", "comment")
                if key in score
            }
    return extracted


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


def _fetch_trace_with_retry(
    client: Any,
    trace_id: str,
    *,
    attempts: int,
    required_score_names: frozenset[str] | None = None,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            trace_payload = client.api.trace.get(trace_id)
            if required_score_names is None:
                return trace_payload
            trace_data = _to_json_data(trace_payload)
            present_score_names = set(_extract_scores(trace_data, required_score_names))
            if required_score_names <= present_score_names:
                return trace_payload
            last_error = RuntimeError(
                "Langfuse score 대기 중: "
                + ", ".join(sorted(required_score_names - present_score_names))
            )
        except Exception as exc:  # noqa: BLE001 - SDK 오류는 재시도 후 명시적으로 처리
            last_error = exc
        if attempt < max(attempts, 1):
            time.sleep(0.5 * attempt)
    raise RuntimeError("Langfuse trace 확인에 실패했습니다.") from last_error


def _fetch_observations_with_retry(
    client: Any,
    trace_id: str,
    *,
    attempts: int,
) -> list[Any]:
    last_error: Exception | None = None
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            response = client.api.observations.get_many(
                trace_id=trace_id,
                limit=100,
                fields=(
                    "core,basic,time,io,metadata,model,usage,prompt,metrics,"
                    "trace_context"
                ),
            )
            observations = response.data
            if observations:
                return list(observations)
        except Exception as exc:  # noqa: BLE001 - SDK 오류는 재시도 후 명시적으로 처리
            last_error = exc
        if attempt < max(attempts, 1):
            time.sleep(0.5 * attempt)
    raise RuntimeError("Langfuse observation 확인에 실패했습니다.") from last_error


def build_parser() -> argparse.ArgumentParser:
    """Langfuse trace 검증 CLI 파서를 생성한다."""
    parser = argparse.ArgumentParser(description="Langfuse trace 적재를 검증합니다.")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--attempts", type=int, default=10)
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
