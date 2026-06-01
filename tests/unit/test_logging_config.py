from __future__ import annotations

import logging

from logging_config import DEFAULT_LOG_LEVEL, PROJECT_LOGGERS, configure_logging


def test_configure_logging_sets_project_logger_levels() -> None:
    for logger_name in PROJECT_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.NOTSET)

    configure_logging()

    for logger_name in PROJECT_LOGGERS:
        project_logger = logging.getLogger(logger_name)
        assert project_logger.level == DEFAULT_LOG_LEVEL
        assert project_logger.propagate is True
