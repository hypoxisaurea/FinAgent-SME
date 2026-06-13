from __future__ import annotations

import logging
from typing import Any

from backend.data.db import WORKFLOW_JOB_TABLE_NAME, create_db_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)


def create_workflow_job(
    *,
    job_id: str,
    request_id: str,
    company_name: str,
    status: str,
    submitted_at: str,
    updated_at: str,
) -> None:
    """워크플로우 job 레코드를 생성한다."""
    engine = create_db_engine()
    try:
        with engine.begin() as connection:
            _ensure_workflow_job_table(connection)
            connection.execute(
                text(
                    f"""
                    INSERT INTO {WORKFLOW_JOB_TABLE_NAME} (
                        job_id,
                        request_id,
                        company_name,
                        status,
                        submitted_at,
                        updated_at
                    )
                    VALUES (
                        :job_id,
                        :request_id,
                        :company_name,
                        :status,
                        :submitted_at,
                        :updated_at
                    )
                    """
                ),
                {
                    "job_id": job_id,
                    "request_id": request_id,
                    "company_name": company_name,
                    "status": status,
                    "submitted_at": submitted_at,
                    "updated_at": updated_at,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_job_create_failed job_id=%s", job_id)
        raise RuntimeError("워크플로우 job 생성에 실패했습니다.") from exc
    finally:
        engine.dispose()


def get_workflow_job(job_id: str) -> dict[str, Any] | None:
    """job_id로 워크플로우 job 레코드를 조회한다."""
    engine = create_db_engine()
    try:
        with engine.begin() as connection:
            _ensure_workflow_job_table(connection)
            row = connection.execute(
                text(
                    f"""
                    SELECT
                        job_id,
                        request_id,
                        company_name,
                        status,
                        result_json,
                        step_summary_json,
                        error_code,
                        error_message,
                        submitted_at,
                        started_at,
                        finished_at,
                        updated_at
                    FROM {WORKFLOW_JOB_TABLE_NAME}
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": job_id},
            ).mappings().first()
        return dict(row) if row is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_job_get_failed job_id=%s", job_id)
        raise RuntimeError("워크플로우 job 조회에 실패했습니다.") from exc
    finally:
        engine.dispose()


def get_next_queued_workflow_job() -> dict[str, Any] | None:
    """가장 먼저 등록된 queued job 하나를 조회한다."""
    engine = create_db_engine()
    try:
        with engine.begin() as connection:
            _ensure_workflow_job_table(connection)
            row = connection.execute(
                text(
                    f"""
                    SELECT
                        job_id,
                        request_id,
                        company_name,
                        status,
                        submitted_at,
                        started_at,
                        finished_at,
                        updated_at
                    FROM {WORKFLOW_JOB_TABLE_NAME}
                    WHERE status = 'queued'
                    ORDER BY submitted_at ASC
                    LIMIT 1
                    """
                )
            ).mappings().first()
        return dict(row) if row is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_job_get_next_queued_failed")
        raise RuntimeError("다음 워크플로우 job 조회에 실패했습니다.") from exc
    finally:
        engine.dispose()


def claim_workflow_job(
    *,
    job_id: str,
    started_at: str,
    updated_at: str,
) -> bool:
    """queued 상태의 job을 running으로 전이한다."""
    engine = create_db_engine()
    try:
        with engine.begin() as connection:
            _ensure_workflow_job_table(connection)
            result = connection.execute(
                text(
                    f"""
                    UPDATE {WORKFLOW_JOB_TABLE_NAME}
                    SET
                        status = 'running',
                        started_at = :started_at,
                        updated_at = :updated_at
                    WHERE job_id = :job_id
                      AND status = 'queued'
                    """
                ),
                {
                    "job_id": job_id,
                    "started_at": started_at,
                    "updated_at": updated_at,
                },
            )
        return bool(result.rowcount)
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_job_claim_failed job_id=%s", job_id)
        raise RuntimeError("워크플로우 job 시작 처리에 실패했습니다.") from exc
    finally:
        engine.dispose()


def complete_workflow_job(
    *,
    job_id: str,
    result_json: str,
    step_summary_json: str,
    finished_at: str,
    updated_at: str,
) -> None:
    """job을 성공 상태로 완료 처리한다."""
    engine = create_db_engine()
    try:
        with engine.begin() as connection:
            _ensure_workflow_job_table(connection)
            connection.execute(
                text(
                    f"""
                    UPDATE {WORKFLOW_JOB_TABLE_NAME}
                    SET
                        status = 'succeeded',
                        result_json = :result_json,
                        step_summary_json = :step_summary_json,
                        finished_at = :finished_at,
                        updated_at = :updated_at,
                        error_code = NULL,
                        error_message = NULL
                    WHERE job_id = :job_id
                    """
                ),
                {
                    "job_id": job_id,
                    "result_json": result_json,
                    "step_summary_json": step_summary_json,
                    "finished_at": finished_at,
                    "updated_at": updated_at,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_job_complete_failed job_id=%s", job_id)
        raise RuntimeError("워크플로우 job 완료 처리에 실패했습니다.") from exc
    finally:
        engine.dispose()


def fail_workflow_job(
    *,
    job_id: str,
    error_code: str,
    error_message: str,
    finished_at: str,
    updated_at: str,
) -> None:
    """job을 실패 상태로 완료 처리한다."""
    engine = create_db_engine()
    try:
        with engine.begin() as connection:
            _ensure_workflow_job_table(connection)
            connection.execute(
                text(
                    f"""
                    UPDATE {WORKFLOW_JOB_TABLE_NAME}
                    SET
                        status = 'failed',
                        error_code = :error_code,
                        error_message = :error_message,
                        finished_at = :finished_at,
                        updated_at = :updated_at
                    WHERE job_id = :job_id
                    """
                ),
                {
                    "job_id": job_id,
                    "error_code": error_code,
                    "error_message": error_message,
                    "finished_at": finished_at,
                    "updated_at": updated_at,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_job_fail_failed job_id=%s", job_id)
        raise RuntimeError("워크플로우 job 실패 처리에 실패했습니다.") from exc
    finally:
        engine.dispose()


def requeue_incomplete_workflow_jobs(updated_at: str) -> int:
    """비정상 종료 등으로 남은 queued/running job을 queued로 재설정한다."""
    engine = create_db_engine()
    try:
        with engine.begin() as connection:
            _ensure_workflow_job_table(connection)
            result = connection.execute(
                text(
                    f"""
                    UPDATE {WORKFLOW_JOB_TABLE_NAME}
                    SET
                        status = 'queued',
                        started_at = NULL,
                        updated_at = :updated_at
                    WHERE status IN ('queued', 'running')
                      AND finished_at IS NULL
                    """
                ),
                {"updated_at": updated_at},
            )
        return int(result.rowcount or 0)
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_job_requeue_failed")
        raise RuntimeError("미완료 워크플로우 job 재설정에 실패했습니다.") from exc
    finally:
        engine.dispose()


def _ensure_workflow_job_table(connection: Any) -> None:
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {WORKFLOW_JOB_TABLE_NAME} (
                job_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                company_name TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NULL,
                step_summary_json TEXT NULL,
                error_code TEXT NULL,
                error_message TEXT NULL,
                submitted_at TEXT NOT NULL,
                started_at TEXT NULL,
                finished_at TEXT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    )
