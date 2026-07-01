"""Analytics dashboard API."""

from fastapi import APIRouter

from app.routers.auth import admin_required
from app.services.analytics import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[admin_required()])


@router.get("/dashboard")
async def get_dashboard_stats() -> dict:
    return await analytics_service.dashboard_stats()
