from __future__ import annotations

import asyncio
import time

from backend.data.services.workflow_job_runner import WorkflowJobRunner


def test_workflow_job_runner_completes_job(monkeypatch) -> None:
    queued_jobs = [
        {
            "job_id": "job-123",
            "request_id": "req-123",
            "company_name": "FinAgent",
        }
    ]
    completed: dict[str, object] = {}

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_incomplete_workflow_jobs",
        lambda: 0,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.get_next_queued_workflow_job",
        lambda: queued_jobs.pop(0) if queued_jobs else None,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.claim_workflow_job",
        lambda job_id: True,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.complete_workflow_job",
        lambda job_id, result: completed.update({"job_id": job_id, "result": result}),
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_workflow_job",
        lambda *args, **kwargs: None,
    )

    def fake_run_credit_workflow(company_name: str, request_id: str) -> dict[str, object]:
        return {
            "request_id": request_id,
            "company_name": company_name,
            "status": "success",
            "context": {},
            "steps": [],
        }

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.run_credit_workflow_in_background",
        fake_run_credit_workflow,
    )

    async def _run() -> None:
        runner = WorkflowJobRunner(poll_interval_seconds=0.01)
        await runner.start()
        runner.notify_job_submitted()
        await asyncio.sleep(0.05)
        await runner.stop()

    asyncio.run(_run())

    assert completed["job_id"] == "job-123"
    assert completed["result"]["status"] == "success"


def test_workflow_job_runner_marks_failure(monkeypatch) -> None:
    queued_jobs = [
        {
            "job_id": "job-456",
            "request_id": "req-456",
            "company_name": "BrokenCorp",
        }
    ]
    failed: dict[str, object] = {}

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_incomplete_workflow_jobs",
        lambda: 0,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.get_next_queued_workflow_job",
        lambda: queued_jobs.pop(0) if queued_jobs else None,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.claim_workflow_job",
        lambda job_id: True,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.complete_workflow_job",
        lambda job_id, result: None,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_workflow_job",
        lambda job_id, **kwargs: failed.update({"job_id": job_id, **kwargs}),
    )

    def fake_run_credit_workflow(company_name: str, request_id: str) -> dict[str, object]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.run_credit_workflow_in_background",
        fake_run_credit_workflow,
    )

    async def _run() -> None:
        runner = WorkflowJobRunner(poll_interval_seconds=0.01)
        await runner.start()
        runner.notify_job_submitted()
        await asyncio.sleep(0.05)
        await runner.stop()

    asyncio.run(_run())

    assert failed["job_id"] == "job-456"
    assert failed["error_code"] == "AGENT_EXECUTION_FAILED"


def test_workflow_job_runner_does_not_mislabel_internal_value_error(monkeypatch) -> None:
    queued_jobs = [
        {
            "job_id": "job-value-error",
            "request_id": "req-value-error",
            "company_name": "FinAgent",
        }
    ]
    failed: dict[str, object] = {}

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_incomplete_workflow_jobs",
        lambda: 0,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.get_next_queued_workflow_job",
        lambda: queued_jobs.pop(0) if queued_jobs else None,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.claim_workflow_job",
        lambda job_id: True,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_workflow_job",
        lambda job_id, **kwargs: failed.update({"job_id": job_id, **kwargs}),
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.run_credit_workflow_in_background",
        lambda company_name, request_id: (_ for _ in ()).throw(
            ValueError("internal response contract failed")
        ),
    )

    async def _run() -> None:
        runner = WorkflowJobRunner(poll_interval_seconds=0.01)
        await runner.start()
        runner.notify_job_submitted()
        await asyncio.sleep(0.05)
        await runner.stop()

    asyncio.run(_run())

    assert failed["job_id"] == "job-value-error"
    assert failed["error_code"] == "AGENT_EXECUTION_FAILED"


def test_workflow_job_runner_start_raises_when_initialization_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_incomplete_workflow_jobs",
        lambda: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )

    async def _run() -> None:
        runner = WorkflowJobRunner(poll_interval_seconds=0.01)
        try:
            await runner.start()
        except RuntimeError as exc:
            assert "job runner" in str(exc)
            return
        raise AssertionError("WorkflowJobRunner.start() should have raised RuntimeError")

    asyncio.run(_run())


def test_workflow_job_runner_notify_restarts_inactive_loop() -> None:
    async def _run() -> None:
        runner = WorkflowJobRunner(poll_interval_seconds=0.01)

        async def fake_run_loop() -> None:
            await asyncio.sleep(0.01)

        runner._run_loop = fake_run_loop  # type: ignore[method-assign]
        runner._task = asyncio.create_task(fake_run_loop())
        await runner._task

        runner.notify_job_submitted()

        assert runner.is_running()
        await runner._task

    asyncio.run(_run())


def test_workflow_job_runner_marks_timeout_failure(monkeypatch) -> None:
    queued_jobs = [
        {
            "job_id": "job-timeout",
            "request_id": "req-timeout",
            "company_name": "SlowCorp",
        }
    ]
    failed: dict[str, object] = {}

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_incomplete_workflow_jobs",
        lambda: 0,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.get_next_queued_workflow_job",
        lambda: queued_jobs.pop(0) if queued_jobs else None,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.claim_workflow_job",
        lambda job_id: True,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.complete_workflow_job",
        lambda job_id, result: None,
    )
    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.workflow_job_service.fail_workflow_job",
        lambda job_id, **kwargs: failed.update({"job_id": job_id, **kwargs}),
    )

    def fake_run_credit_workflow(company_name: str, request_id: str) -> dict[str, object]:
        time.sleep(0.05)
        return {
            "request_id": request_id,
            "company_name": company_name,
            "status": "success",
            "context": {},
            "steps": [],
        }

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.run_credit_workflow_in_background",
        fake_run_credit_workflow,
    )

    async def _run() -> None:
        runner = WorkflowJobRunner(
            poll_interval_seconds=0.01,
            job_timeout_seconds=0.01,
        )
        await runner.start()
        runner.notify_job_submitted()
        await asyncio.sleep(0.05)
        await runner.stop()

    asyncio.run(_run())

    assert failed["job_id"] == "job-timeout"
    assert failed["error_code"] == "AGENT_TIMEOUT"
