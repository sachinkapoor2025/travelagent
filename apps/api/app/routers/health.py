"""Health and status endpoints."""

from fastapi import APIRouter

from app.config import get_settings
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, environment=settings.app_env)
