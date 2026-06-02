from __future__ import annotations

import logging
from typing import Any

from backend.data.db import create_db_engine
from sqlalchemy import inspect, text


def fetch_rows(
    *,
    logger: logging.Logger,
    query: str,
    params: dict[str, Any],
    table_name: str,
    error_message: str,
    missing_table_error_message: str | None = None,
) -> list[dict[str, Any]]:
    """테이블 존재 여부를 확인한 뒤 조회 결과를 dict 목록으로 반환한다."""
    engine = create_db_engine()
    try:
        inspector = inspect(engine)
        if not inspector.has_table(table_name):
            logger.info("repository_table_missing table=%s", table_name)
            if missing_table_error_message is not None:
                raise RuntimeError(missing_table_error_message)
            return []

        with engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()

        return [dict(row) for row in rows]
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("repository_query_failed table=%s", table_name)
        raise RuntimeError(error_message) from exc
    finally:
        engine.dispose()
