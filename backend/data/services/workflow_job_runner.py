from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import backend.data.services.workflow_job_service as workflow_job_service
from backend.agents.orchestrator.orchestrator import run_credit_workflow
from backend.common.settings import settings

logger = logging.getLogger(__name__)


def run_credit_workflow_in_background(
    company_name: str,
    request_id: str,
) -> dict[str, Any]:
    """별도 스레드에서 workflow coroutine을 독립 이벤트 루프로 실행한다."""
    return asyncio.run(
        run_credit_workflow(
            company_name,
            extra_payload={"request_id": request_id},
        )
    )


class WorkflowJobRunner:
    """DB에 등록된 queued workflow job을 백그라운드에서 처리한다."""

    def __init__(
        self,
        *,
        poll_interval_seconds: float = 1.0,
        job_timeout_seconds: float = 300.0,
    ) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._job_timeout_seconds = job_timeout_seconds
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self._last_error: str | None = None
        self._last_error_at: str | None = None
        self._current_job: dict[str, str] | None = None

    async def start(self) -> None:
        """백그라운드 worker loop를 시작한다."""
        if self._task is not None and not self._task.done():
            return
        self._stop_requested = False
        self._last_error = None
        self._last_error_at = None
        try:
            failed_count = await asyncio.to_thread(
                workflow_job_service.fail_incomplete_workflow_jobs
            )
        except Exception as exc:  # noqa: BLE001
            self._record_error(exc)
            logger.exception("workflow_job_runner_start_failed")
            raise RuntimeError(
                "워크플로우 job runner를 시작하지 못했습니다."
            ) from exc
        logger.info("workflow_job_runner_started failed_incomplete_count=%s", failed_count)
        self._task = asyncio.create_task(self._run_loop())
        self.notify_job_submitted()

    async def stop(self) -> None:
        """백그라운드 worker loop를 종료한다."""
        self._stop_requested = True
        self._wake_event.set()
        if self._task is not None:
            await self._task
            self._task = None
        logger.info("workflow_job_runner_stopped")

    def notify_job_submitted(self) -> None:
        """신규 job 등록 시 worker가 즉시 깨어나도록 알린다."""
        if self._stop_requested:
            return
        if self._task is None or self._task.done():
            logger.warning("workflow_job_runner_inactive_restart_requested")
            self._start_background_loop_if_possible()
        self._wake_event.set()

    def is_running(self) -> bool:
        """worker loop가 현재 살아 있는지 반환한다."""
        return self._task is not None and not self._task.done()

    def get_status(self) -> dict[str, object]:
        """worker 상태를 진단용으로 반환한다."""
        return {
            "running": self.is_running(),
            "stop_requested": self._stop_requested,
            "job_timeout_seconds": self._job_timeout_seconds,
            "last_error": self._last_error,
            "last_error_at": self._last_error_at,
            "current_job": self._current_job,
        }

    async def _run_loop(self) -> None:
        while not self._stop_requested:
            try:
                job = await asyncio.to_thread(
                    workflow_job_service.get_next_queued_workflow_job
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("workflow_job_runner_poll_failed error=%s", exc)
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            if job is None:
                self._wake_event.clear()
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(),
                        timeout=self._poll_interval_seconds,
                    )
                except TimeoutError:
                    continue
                continue

            job_id = str(job["job_id"])
            try:
                claimed = await asyncio.to_thread(
                    workflow_job_service.claim_workflow_job,
                    job_id,
                )
                if not claimed:
                    continue

                await self._execute_job(
                    job_id,
                    str(job["company_name"]),
                    str(job["request_id"]),
                )
            except Exception as exc:  # noqa: BLE001
                self._record_error(exc)
                logger.exception(
                    "workflow_job_runner_iteration_failed job_id=%s",
                    job_id,
                )
                await asyncio.sleep(self._poll_interval_seconds)

    async def _execute_job(
        self,
        job_id: str,
        company_name: str,
        request_id: str,
    ) -> None:
        self._current_job = {
            "job_id": job_id,
            "company_name": company_name,
            "request_id": request_id,
            "started_at": datetime.now(UTC).isoformat(),
        }
        logger.info(
            "workflow_job_started job_id=%s company_name=%s request_id=%s",
            job_id,
            company_name,
            request_id,
        )
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    run_credit_workflow_in_background,
                    company_name,
                    request_id,
                ),
                timeout=self._job_timeout_seconds,
            )
            await asyncio.to_thread(
                workflow_job_service.complete_workflow_job,
                job_id,
                result,
            )
            logger.info(
                "workflow_job_completed job_id=%s company_name=%s",
                job_id,
                company_name,
            )
        except ValueError as exc:
            await asyncio.to_thread(
                workflow_job_service.fail_workflow_job,
                job_id,
                error_code="INVALID_INPUT",
                error_message=str(exc),
            )
            logger.info(
                "workflow_job_invalid_input job_id=%s company_name=%s error=%s",
                job_id,
                company_name,
                exc,
            )
        except TimeoutError as exc:
            self._record_error(exc)
            logger.exception(
                "workflow_job_timeout job_id=%s company_name=%s timeout_seconds=%s",
                job_id,
                company_name,
                self._job_timeout_seconds,
            )
            await asyncio.to_thread(
                workflow_job_service.fail_workflow_job,
                job_id,
                error_code="AGENT_TIMEOUT",
                error_message=(
                    f"workflow job timed out after {self._job_timeout_seconds} seconds"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._record_error(exc)
            logger.exception(
                "workflow_job_failed job_id=%s company_name=%s",
                job_id,
                company_name,
            )
            await asyncio.to_thread(
                workflow_job_service.fail_workflow_job,
                job_id,
                error_code="AGENT_EXECUTION_FAILED",
                error_message=str(exc),
            )
        finally:
            self._current_job = None

    def _record_error(self, exc: Exception) -> None:
        self._last_error = str(exc)
        self._last_error_at = datetime.now(UTC).isoformat()

    def _start_background_loop_if_possible(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("workflow_job_runner_restart_skipped_no_event_loop")
            return

        self._task = loop.create_task(self._run_loop())
        logger.info("workflow_job_runner_restarted")


workflow_job_runner = WorkflowJobRunner(
    job_timeout_seconds=settings.workflow_job_timeout_seconds
)
