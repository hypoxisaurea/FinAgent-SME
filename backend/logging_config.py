from __future__ import annotations

import logging
import os

DEFAULT_LOG_LEVEL_NAME = os.getenv("FINAGENT_LOG_LEVEL", "INFO").upper()
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
PROJECT_LOGGERS = (
    "api",
    "agents",
    "services",
)


def _resolve_log_level(level_name: str) -> int:
    return getattr(logging, level_name, logging.INFO)


def configure_logging(level: int | None = None) -> None:
    """프로젝트 로거가 콘솔에 구조화된 진행 로그를 출력하도록 설정한다."""
    resolved_level = level if level is not None else _resolve_log_level(
        DEFAULT_LOG_LEVEL_NAME
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(resolved_level)
        console_handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
        root_logger.addHandler(console_handler)

    for logger_name in PROJECT_LOGGERS:
        project_logger = logging.getLogger(logger_name)
        project_logger.setLevel(resolved_level)
        project_logger.propagate = True
