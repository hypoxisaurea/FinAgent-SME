from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
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

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OPEN_ROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPEN_ROUTER_MODEL = "openai/gpt-4o-mini"
PRIMARY_LLM_API_KEY_ENV_NAMES = ("OPEN_ROUTER_API_KEY", "OPENROUTER_API_KEY")
LEGACY_LLM_API_KEY_ENV_NAMES = ("OPEN_AI_API_KEY", "OPENAI_API_KEY", "OPEN_API_KEY")


@dataclass(frozen=True, slots=True)
class LLMClientConfig:
    api_key: str
    provider: str
    base_url: str | None = None
    default_headers: dict[str, str] | None = None


def _get_env_value(*env_names: str) -> str:
    for env_name in env_names:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return ""


def _build_open_router_headers() -> dict[str, str] | None:
    headers: dict[str, str] = {}

    site_url = _get_env_value("OPEN_ROUTER_SITE_URL", "OPENROUTER_SITE_URL")
    app_name = _get_env_value("OPEN_ROUTER_APP_NAME", "OPENROUTER_APP_NAME")

    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name

    return headers or None


def get_model_name() -> str:
    model_name = _get_env_value(
        "OPEN_ROUTER_MODEL",
        "OPENROUTER_MODEL",
        "OPENAI_MODEL",
    )
    if model_name:
        return model_name

    if _get_env_value(*PRIMARY_LLM_API_KEY_ENV_NAMES):
        return DEFAULT_OPEN_ROUTER_MODEL

    return DEFAULT_OPENAI_MODEL


def get_llm_client_config() -> LLMClientConfig:
    open_router_key = _get_env_value(*PRIMARY_LLM_API_KEY_ENV_NAMES)
    if open_router_key:
        base_url = _get_env_value("OPEN_ROUTER_BASE_URL", "OPENROUTER_BASE_URL")
        return LLMClientConfig(
            api_key=open_router_key,
            provider="openrouter",
            base_url=base_url or DEFAULT_OPEN_ROUTER_BASE_URL,
            default_headers=_build_open_router_headers(),
        )

    for legacy_env_name in LEGACY_LLM_API_KEY_ENV_NAMES:
        legacy_key = _get_env_value(legacy_env_name)
        if legacy_key:
            logger.warning(
                "legacy_llm_api_key_used env_var=%s preferred=OPEN_ROUTER_API_KEY",
                legacy_env_name,
            )
            return LLMClientConfig(api_key=legacy_key, provider="openai")

    raise EnvironmentError(
        "LLM API 키가 설정되지 않았습니다. "
        "신규 설정은 OPEN_ROUTER_API_KEY를 사용하고, "
        "호환용으로 OPEN_AI_API_KEY, OPENAI_API_KEY, OPEN_API_KEY도 허용됩니다."
    )


def get_api_key() -> str:
    return get_llm_client_config().api_key


def build_llm_client_kwargs(*, timeout: int | None = None) -> dict[str, Any]:
    config = get_llm_client_config()
    client_kwargs: dict[str, Any] = {
        "api_key": config.api_key,
    }
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    if config.base_url:
        client_kwargs["base_url"] = config.base_url
    if config.default_headers:
        client_kwargs["default_headers"] = config.default_headers
    return client_kwargs


@asynccontextmanager
async def get_client(timeout: int = 60) -> AsyncGenerator[Any, None]:
    client_class = get_async_openai_class()
    client = client_class(
        **build_llm_client_kwargs(timeout=timeout),
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
        "model": get_model_name(),
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
        raise ValueError("LLM 응답 content가 비어 있습니다.")
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
