"""Proactive disruption monitoring — serverless worker job (no extra AWS resources)."""

import logging
from typing import Any

from app.services.whatsapp import whatsapp_service
from app.storage.bookings_repo import booking_repo
from app.storage.dynamo import events_store, now_iso

logger = logging.getLogger("travel-ai-disruption")


async def check_disruptions() -> dict[str, Any]:
    """Scan recent bookings and notify travelers of simulated/real disruptions."""
    bookings = await booking_repo.list_recent(limit=30)
    notified = 0
    store = events_store()

    for booking in bookings:
        if booking.get("status") not in ("held", "confirmed", "paid"):
            continue
        booking_id = booking["id"]
        event_key = f"DISRUPTION#{booking_id}"
        if store.enabled and store.get(event_key, "METADATA"):
            continue

        phone = await booking_repo.get_lead_phone(booking.get("lead_id"))
        if not phone:
            continue

        origin = booking.get("origin", "")
        destination = booking.get("destination", "")
        message = (
            f"TravelAI Alert: We're monitoring your {origin}→{destination} trip. "
            f"If your flight is delayed or cancelled, reply REBOOK and Sarah will find alternatives. "
            f"Booking ref: {booking.get('pnr') or booking_id[:8]}"
        )
        await whatsapp_service.send_text(phone, message)
        if store.enabled:
            store.put(event_key, "METADATA", {"booking_id": booking_id, "notified_at": now_iso()})
        notified += 1

    return {"checked": len(bookings), "notified": notified}
