from backend.api.routes import health, workflows
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(workflows.router)
