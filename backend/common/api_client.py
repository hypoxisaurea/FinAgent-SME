from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from backend.common.env import load_backend_env
from backend.common.langfuse import (
    build_openai_trace_kwargs,
    get_async_openai_class,
)
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

load_backend_env()

logger = logging.getLogger(__name__)

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def get_api_key() -> str:
    key = os.environ.get("OPEN_AI_API_KEY", "").strip()
    if key:
        return key

    legacy_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if legacy_key:
        logger.warning(
            "legacy_openai_api_key_used "
            "env_var=OPENAI_API_KEY preferred=OPEN_AI_API_KEY"
        )
        return legacy_key

    older_legacy_key = os.environ.get("OPEN_API_KEY", "").strip()
    if older_legacy_key:
        logger.warning(
            "legacy_openai_api_key_used env_var=OPEN_API_KEY preferred=OPEN_AI_API_KEY"
        )
        return older_legacy_key

    raise EnvironmentError(
        "OPEN_AI_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인해주세요."
    )


@asynccontextmanager
async def get_client(timeout: int = 60) -> AsyncGenerator[Any, None]:
    client_class = get_async_openai_class()
    client = client_class(
        api_key=get_api_key(),
        timeout=timeout,
        max_retries=0,
    )
    try:
        yield client
    finally:
        await client.close()


openai_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(
        (APITimeoutError, APIConnectionError, APIStatusError, RateLimitError)
    ),
    reraise=True,
)


@openai_retry
async def call_openai(
    client: Any,
    messages: list[dict[str, Any]],
    system: str,
    max_tokens: int = 1000,
    response_format: dict[str, str] | None = None,
    observation_name: str | None = None,
    request_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    request_messages = [{"role": "system", "content": system}, *messages]
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": request_messages,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    payload.update(
        build_openai_trace_kwargs(
            name=observation_name,
            session_id=request_id,
            tags=tags,
            metadata=metadata,
        )
    )
    if response_format is not None:
        payload["response_format"] = response_format

    resp = await client.chat.completions.create(**payload)
    content = resp.choices[0].message.content
    if content is None:
        raise ValueError("OpenAI 응답 content가 비어 있습니다.")
    return content


def parse_json_response(raw: str) -> dict | list:
    clean = (
        raw.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    return json.loads(clean)
