"""Price alert endpoints."""

from fastapi import APIRouter

from app.schemas import PriceAlertCreate, PriceAlertResponse
from app.services.price_alerts import price_alert_service

router = APIRouter(prefix="/price-alerts", tags=["price-alerts"])


@router.post("", response_model=PriceAlertResponse, status_code=201)
async def create_price_alert(payload: PriceAlertCreate) -> PriceAlertResponse:
    return await price_alert_service.create(payload)


@router.get("", response_model=list[PriceAlertResponse])
async def list_price_alerts() -> list[PriceAlertResponse]:
    alerts = await price_alert_service.list_active()
    return [
        PriceAlertResponse(
            alert_id=a.get("alert_id", ""),
            phone=a.get("phone", ""),
            email=a.get("email"),
            origin=a.get("origin", ""),
            destination=a.get("destination", ""),
            departure_date=a.get("departure_date", ""),
            target_price=float(a.get("target_price", 0)),
            market=a.get("market", "uae"),
            status=a.get("status", "active"),
            last_checked_price=a.get("last_checked_price"),
            created_at=a.get("created_at", ""),
        )
        for a in alerts
    ]
