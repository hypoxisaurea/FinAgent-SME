from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from importlib import import_module
from typing import Any

from backend.common.env import load_backend_env
from openai import AsyncOpenAI as BaseAsyncOpenAI
from openai import OpenAI as BaseOpenAI

load_backend_env()

logger = logging.getLogger(__name__)

LANGFUSE_PUBLIC_KEY_ENV_NAME = "LANGFUSE_PUBLIC_KEY"
LANGFUSE_SECRET_KEY_ENV_NAME = "LANGFUSE_SECRET_KEY"
LANGFUSE_ENABLE_IN_TESTS_ENV_NAME = "FINAGENT_ENABLE_LANGFUSE_IN_TESTS"


class _NoopObservation:
    """Langfuse 비활성화 시 update 호출을 흡수하는 no-op 객체."""

    def update(
        self,
        *,
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        return None


@lru_cache(maxsize=1)
def _has_langfuse_sdk() -> bool:
    try:
        import langfuse  # noqa: F401
    except ImportError:
        return False
    return True


def _has_langfuse_credentials() -> bool:
    public_key = os.getenv(LANGFUSE_PUBLIC_KEY_ENV_NAME, "").strip()
    secret_key = os.getenv(LANGFUSE_SECRET_KEY_ENV_NAME, "").strip()
    return bool(public_key and secret_key)


def _is_test_runtime() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ


def is_langfuse_enabled() -> bool:
    """Langfuse SDK와 필수 자격증명이 모두 준비됐는지 반환한다."""
    if _is_test_runtime():
        allow_in_tests = os.getenv(LANGFUSE_ENABLE_IN_TESTS_ENV_NAME, "").strip().lower()
        if allow_in_tests not in {"1", "true", "yes", "on"}:
            return False
    return _has_langfuse_sdk() and _has_langfuse_credentials()


def get_langfuse_client() -> Any | None:
    """활성화된 경우 Langfuse client를 반환하고, 아니면 None을 반환한다."""
    if not is_langfuse_enabled():
        return None

    from langfuse import get_client

    return get_client()


@contextmanager
def start_as_current_observation(
    *,
    name: str,
    as_type: str,
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Langfuse observation을 시작하고, 비활성화 시 no-op으로 대체한다."""
    client = get_langfuse_client()
    if client is None:
        yield _NoopObservation()
        return

    with client.start_as_current_observation(
        name=name,
        as_type=as_type,
        input=input,
        metadata=metadata,
    ) as observation:
        yield observation


def shutdown_langfuse() -> None:
    """서버 종료 시 Langfuse 버퍼를 안전하게 비운다."""
    client = get_langfuse_client()
    if client is None:
        return
    client.shutdown()


@contextmanager
def propagate_trace_attributes(
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    """현재 실행 컨텍스트의 Langfuse trace 속성을 전파한다."""
    if not is_langfuse_enabled():
        yield
        return

    from langfuse import propagate_attributes

    with propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        tags=tags,
        metadata=metadata,
    ):
        yield


def get_async_openai_class() -> type[Any]:
    """환경에 따라 Langfuse 래핑 AsyncOpenAI 또는 기본 AsyncOpenAI를 반환한다."""
    if is_langfuse_enabled():
        try:
            return getattr(import_module("langfuse.openai"), "AsyncOpenAI")
        except ImportError:
            logger.warning("langfuse_async_openai_wrapper_unavailable")
    return BaseAsyncOpenAI


def get_openai_class() -> type[Any]:
    """환경에 따라 Langfuse 래핑 OpenAI 또는 기본 OpenAI를 반환한다."""
    if is_langfuse_enabled():
        try:
            return getattr(import_module("langfuse.openai"), "OpenAI")
        except ImportError:
            logger.warning("langfuse_openai_wrapper_unavailable")
    return BaseOpenAI


def build_openai_trace_kwargs(
    *,
    name: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Langfuse OpenAI wrapper가 읽는 tracing용 추가 인자를 구성한다."""
    if not is_langfuse_enabled():
        return {}

    langfuse_metadata = {
        key: value
        for key, value in (metadata or {}).items()
        if value is not None
    }

    trace_metadata: dict[str, Any] = {}
    if session_id:
        trace_metadata["langfuse_session_id"] = str(session_id)
    if tags:
        trace_metadata["langfuse_tags"] = tags
    if langfuse_metadata:
        trace_metadata["langfuse_metadata"] = langfuse_metadata

    kwargs: dict[str, Any] = {}
    if name:
        kwargs["name"] = name
    if trace_metadata:
        kwargs["metadata"] = trace_metadata
    return kwargs
