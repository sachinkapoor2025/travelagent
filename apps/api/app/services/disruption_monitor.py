"""Proactive disruption monitoring + self-healing rebooking."""

import logging
from typing import Any

from app.services.travel_tools import execute_tool
from app.services.whatsapp import whatsapp_service
from app.storage.bookings_repo import booking_repo
from app.storage.dynamo import events_store, now_iso

logger = logging.getLogger("travel-ai-disruption")


async def check_disruptions() -> dict[str, Any]:
    bookings = await booking_repo.list_recent(limit=30)
    notified = 0
    rebooked = 0
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

        session_id = f"rebook_{booking_id}"
        rebook_result = await _attempt_rebook(session_id, booking, phone)
        if rebook_result.get("status") == "alternatives_found":
            alt_msg = (
                f"Self-healing update: We found alternative flights for {origin}→{destination}. "
                f"Reply BOOK to confirm the best option."
            )
            await whatsapp_service.send_text(phone, alt_msg)
            rebooked += 1

        if store.enabled:
            store.put(
                event_key,
                "METADATA",
                {"booking_id": booking_id, "notified_at": now_iso(), "rebooked": rebooked > 0},
            )
        notified += 1

    return {"checked": len(bookings), "notified": notified, "rebook_alternatives": rebooked}


async def _attempt_rebook(session_id: str, booking: dict[str, Any], phone: str) -> dict[str, Any]:
    try:
        result = await execute_tool(
            session_id,
            "search_flights",
            {
                "origin": booking.get("origin", "DXB"),
                "destination": booking.get("destination", "BOM"),
                "departure_date": booking.get("departure_date", "2026-08-01"),
                "passengers": booking.get("passengers", 1),
            },
            {"phone": phone, "market": booking.get("market", "uae"), "lead_id": booking.get("lead_id")},
        )
        offers = result.get("offers") or []
        if offers:
            return {"status": "alternatives_found", "offers": offers[:3]}
    except Exception as exc:
        logger.warning("Rebook search failed: %s", exc)
    return {"status": "no_alternatives"}
