"""Analytics dashboard API."""

from fastapi import APIRouter

from app.services.analytics import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard")
async def get_dashboard_stats() -> dict:
    return await analytics_service.dashboard_stats()
