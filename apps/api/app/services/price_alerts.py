"""Flight price drop alerts."""

from typing import Any, Optional
from uuid import uuid4

from app.config import get_settings
from app.schemas import FlightSearchRequest, PriceAlertCreate, PriceAlertResponse
from app.services.booking import duffel_client
from app.services.whatsapp import WhatsAppService
from app.storage.dynamo import DynamoStore, now_iso

settings = get_settings()
whatsapp = WhatsAppService()


class PriceAlertService:
    def __init__(self) -> None:
        self.store = DynamoStore(settings.price_alerts_table)

    async def create(self, req: PriceAlertCreate) -> PriceAlertResponse:
        alert_id = str(uuid4())
        record = {
            "alert_id": alert_id,
            "phone": req.phone,
            "email": req.email,
            "origin": req.origin.upper(),
            "destination": req.destination.upper(),
            "departure_date": req.departure_date,
            "target_price": req.target_price,
            "market": req.market.value,
            "status": "active",
            "last_checked_price": None,
            "created_at": now_iso(),
        }
        if self.store.enabled:
            self.store.put(
                f"ALERT#{alert_id}",
                "METADATA",
                record,
                gsi1pk="ACTIVE_ALERTS",
                gsi1sk=now_iso(),
            )
        return PriceAlertResponse(**record)

    async def list_active(self) -> list[dict[str, Any]]:
        if not self.store.enabled:
            return []
        return self.store.query_gsi1("ACTIVE_ALERTS", limit=100)

    async def check_all(self) -> dict[str, Any]:
        alerts = await self.list_active()
        triggered = 0
        checked = 0

        for alert in alerts:
            checked += 1
            current_price = await self._get_current_price(alert)
            if current_price is None:
                continue

            alert_id = alert.get("alert_id")
            self.store.update(f"ALERT#{alert_id}", "METADATA", {"last_checked_price": current_price})

            target = alert.get("target_price")
            if target and current_price <= target:
                await self._notify_triggered(alert, current_price)
                self.store.update(f"ALERT#{alert_id}", "METADATA", {"status": "triggered"})
                triggered += 1

        return {"checked": checked, "triggered": triggered}

    async def _get_current_price(self, alert: dict[str, Any]) -> Optional[float]:
        try:
            search = FlightSearchRequest(
                origin=alert["origin"],
                destination=alert["destination"],
                departure_date=alert["departure_date"],
                passengers=1,
                market=alert.get("market", "uae"),
            )
            results = await duffel_client.search_flights(search)
            if results.offers:
                return results.offers[0].price
        except Exception:
            pass
        return None

    async def _notify_triggered(self, alert: dict[str, Any], price: float) -> None:
        msg = (
            f"🎉 Price alert triggered!\n"
            f"{alert['origin']} → {alert['destination']} on {alert['departure_date']}\n"
            f"Current price: {price} (target: {alert['target_price']})\n"
            f"Book now before it goes up!"
        )
        if alert.get("phone"):
            await whatsapp.send_text(alert["phone"], msg)


price_alert_service = PriceAlertService()


async def check_price_alerts() -> dict[str, Any]:
    return await price_alert_service.check_all()
