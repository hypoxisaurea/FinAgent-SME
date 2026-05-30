from __future__ import annotations

import logging

DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
PROJECT_LOGGERS = (
    "api",
    "agents",
    "services",
)


def configure_logging(level: int = DEFAULT_LOG_LEVEL) -> None:
    """프로젝트 로거가 콘솔에 INFO 이상 로그를 출력하도록 설정한다."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
        root_logger.addHandler(console_handler)

    for logger_name in PROJECT_LOGGERS:
        project_logger = logging.getLogger(logger_name)
        project_logger.setLevel(level)
        project_logger.propagate = True
