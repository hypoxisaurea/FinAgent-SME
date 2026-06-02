from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

DEFAULT_LOG_LEVEL_NAME = os.getenv("FINAGENT_LOG_LEVEL", "INFO").upper()
DEFAULT_LOG_LEVEL = getattr(logging, DEFAULT_LOG_LEVEL_NAME, logging.INFO)
DEFAULT_REQUEST_ID = "-"
DEFAULT_LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | request_id=%(request_id)s | %(message)s"
)
PROJECT_LOGGERS = (
    "backend",
)
_REQUEST_ID_CONTEXT: ContextVar[str] = ContextVar(
    "finagent_request_id",
    default=DEFAULT_REQUEST_ID,
)
_ORIGINAL_LOG_RECORD_FACTORY = logging.getLogRecordFactory()


class RequestIdFilter(logging.Filter):
    """현재 실행 컨텍스트의 request_id를 모든 로그 레코드에 주입한다."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def _resolve_log_level(level_name: str) -> int:
    return getattr(logging, level_name, logging.INFO)


def get_request_id() -> str:
    """현재 실행 컨텍스트에 바인딩된 request_id를 반환한다."""
    return _REQUEST_ID_CONTEXT.get()


def bind_request_id(request_id: str | None) -> Token[str]:
    """현재 실행 컨텍스트에 request_id를 바인딩한다."""
    normalized_request_id = str(request_id).strip() if request_id else DEFAULT_REQUEST_ID
    return _REQUEST_ID_CONTEXT.set(normalized_request_id or DEFAULT_REQUEST_ID)


def reset_request_id(token: Token[str]) -> None:
    """이전 request_id 컨텍스트를 복구한다."""
    _REQUEST_ID_CONTEXT.reset(token)


@contextmanager
def request_id_context(request_id: str | None) -> Iterator[str]:
    """request_id를 현재 컨텍스트에 바인딩한 채 코드를 실행한다."""
    token = bind_request_id(request_id)
    try:
        yield get_request_id()
    finally:
        reset_request_id(token)


def _request_id_log_record_factory(*args: object, **kwargs: object) -> logging.LogRecord:
    record = _ORIGINAL_LOG_RECORD_FACTORY(*args, **kwargs)
    record.request_id = get_request_id()
    return record


def _configure_log_record_factory() -> None:
    current_factory = logging.getLogRecordFactory()
    if current_factory is not _request_id_log_record_factory:
        logging.setLogRecordFactory(_request_id_log_record_factory)


def _has_request_id_filter(handler: logging.Handler) -> bool:
    return any(isinstance(filter_, RequestIdFilter) for filter_ in handler.filters)


def configure_logging(level: int | None = None) -> None:
    """프로젝트 로거가 콘솔에 구조화된 진행 로그를 출력하도록 설정한다."""
    resolved_level = level if level is not None else DEFAULT_LOG_LEVEL
    _configure_log_record_factory()
    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        root_logger.addHandler(console_handler)

    for handler in root_logger.handlers:
        handler.setLevel(resolved_level)
        handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
        if not _has_request_id_filter(handler):
            handler.addFilter(RequestIdFilter())

    for logger_name in PROJECT_LOGGERS:
        project_logger = logging.getLogger(logger_name)
        project_logger.setLevel(resolved_level)
        project_logger.propagate = True
