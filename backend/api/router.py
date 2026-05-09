from fastapi import APIRouter

from api.routes import health, workflows

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(workflows.router)
