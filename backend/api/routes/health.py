from backend.data.services.workflow_job_runner import workflow_job_runner
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "workflow_job_runner": workflow_job_runner.get_status(),
    }
