from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL              = "claude-sonnet-4-20250514"


def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. "
            ".env 파일을 확인해주세요."
        )
    return key


def get_headers() -> dict[str, str]:
    return {
        "x-api-key":         get_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }


@asynccontextmanager
async def get_client(timeout: int = 60) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    ) as client:
        yield client


claude_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True,
)


@claude_retry
async def call_claude(
    client: httpx.AsyncClient,
    messages: list[dict],
    system: str,
    max_tokens: int = 1000,
) -> str:
    resp = await client.post(
        ANTHROPIC_API_URL,
        headers=get_headers(),
        json={
            "model":      MODEL,
            "max_tokens": max_tokens,
            "system":     system,
            "messages":   messages,
        },
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def parse_json_response(raw: str) -> dict | list:
    import json
    clean = (
        raw.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    return json.loads(clean)