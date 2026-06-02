from __future__ import annotations

import logging

from backend.logging_config import (
    DEFAULT_LOG_LEVEL,
    PROJECT_LOGGERS,
    configure_logging,
    request_id_context,
)


def test_configure_logging_sets_project_logger_levels() -> None:
    for logger_name in PROJECT_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.NOTSET)

    configure_logging()

    for logger_name in PROJECT_LOGGERS:
        project_logger = logging.getLogger(logger_name)
        assert project_logger.level == DEFAULT_LOG_LEVEL
        assert project_logger.propagate is True


def test_configure_logging_injects_request_id_into_log_records(
    caplog,
) -> None:
    configure_logging()
    logger = logging.getLogger("backend.tests.logging")

    with request_id_context("req-unit-test"):
        with caplog.at_level(logging.INFO, logger="backend.tests.logging"):
            logger.info("logging_context_ready")

    assert caplog.records[-1].request_id == "req-unit-test"
    assert caplog.records[-1].message == "logging_context_ready"
