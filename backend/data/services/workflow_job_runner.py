from __future__ import annotations

import asyncio
import logging

from backend.agents.orchestrator import run_credit_workflow
from backend.data.services import workflow_job_service

logger = logging.getLogger(__name__)


class WorkflowJobRunner:
    """DB에 등록된 queued workflow job을 백그라운드에서 처리한다."""

    def __init__(self, *, poll_interval_seconds: float = 1.0) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False

    async def start(self) -> None:
        """백그라운드 worker loop를 시작한다."""
        if self._task is not None and not self._task.done():
            return
        self._stop_requested = False
        try:
            requeued_count = await asyncio.to_thread(
                workflow_job_service.requeue_incomplete_workflow_jobs
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("workflow_job_runner_disabled error=%s", exc)
            return
        logger.info("workflow_job_runner_started requeued_count=%s", requeued_count)
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
        self._wake_event.set()

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
            claimed = await asyncio.to_thread(
                workflow_job_service.claim_workflow_job,
                job_id,
            )
            if not claimed:
                continue

            await self._execute_job(job_id, str(job["company_name"]), str(job["request_id"]))

    async def _execute_job(
        self,
        job_id: str,
        company_name: str,
        request_id: str,
    ) -> None:
        logger.info(
            "workflow_job_started job_id=%s company_name=%s request_id=%s",
            job_id,
            company_name,
            request_id,
        )
        try:
            result = await run_credit_workflow(
                company_name,
                extra_payload={"request_id": request_id},
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
        except Exception as exc:  # noqa: BLE001
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


workflow_job_runner = WorkflowJobRunner()
