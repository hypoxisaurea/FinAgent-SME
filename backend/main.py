import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from backend.api.router import api_router
from backend.common.langfuse import shutdown_langfuse
from backend.common.logging import configure_logging, request_id_context
from backend.common.settings import settings
from backend.data.services.workflow_job_runner import workflow_job_runner
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    try:
        await workflow_job_runner.start()
        yield
    finally:
        await workflow_job_runner.stop()
        shutdown_langfuse()


app = FastAPI(
    title="FinAgent-SME API",
    description="FinAgent-SME B2B 거래 리스크 심사 Multi-Agent System 백엔드",
    version="0.1.0",
    lifespan=app_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.middleware("http")
async def bind_request_id_middleware(
    request: Request,
    call_next,
) -> Response:
    request_id = request.headers.get("x-request-id", "").strip() or f"req-{uuid4().hex[:12]}"
    request.state.request_id = request_id

    with request_id_context(request_id):
        response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/")
def root() -> dict[str, str]:
    logger.info("root_endpoint_requested")
    return {"service": "finagent-sme", "docs": "/docs", "health": "/api/health"}
