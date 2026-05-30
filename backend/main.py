import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import api_router
from config import settings
from logging_config import configure_logging

configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="FinAgent-SME API",
    description="FinAgent-SME B2B 거래 리스크 심사 Multi-Agent System 백엔드",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    logger.info("root_endpoint_requested")
    return {"service": "finagent-sme", "docs": "/docs", "health": "/api/health"}
