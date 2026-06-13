from __future__ import annotations

import asyncio

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
        "backend.data.services.workflow_job_runner.workflow_job_service.requeue_incomplete_workflow_jobs",
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

    async def fake_run_credit_workflow(company_name: str, *, extra_payload: dict[str, str]):
        return {
            "request_id": extra_payload["request_id"],
            "company_name": company_name,
            "status": "success",
            "context": {},
            "steps": [],
        }

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.run_credit_workflow",
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
        "backend.data.services.workflow_job_runner.workflow_job_service.requeue_incomplete_workflow_jobs",
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

    async def fake_run_credit_workflow(company_name: str, *, extra_payload: dict[str, str]):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "backend.data.services.workflow_job_runner.run_credit_workflow",
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
