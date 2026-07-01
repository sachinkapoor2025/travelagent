"""Agentic booking — autonomous search → select → book → pay loop."""

from typing import Any, Optional
from uuid import uuid4

from app.models import Market
from app.services.session import session_store
from app.services.travel_tools import execute_tool


AGENTIC_SYSTEM_ADDON = """
You are in AGENTIC mode: autonomously complete bookings without asking unnecessary confirmations.
When the user wants to book:
1. search_flights with their route
2. Pick the best offer (lowest price, acceptable stops)
3. create_booking with that offer_id
4. send_payment_link immediately
Report each step briefly in one final message."""


class AgenticBookingService:
    async def run_booking_loop(
        self,
        session_id: str,
        origin: str,
        destination: str,
        departure_date: str,
        passengers: int = 1,
        phone: Optional[str] = None,
        market: Market = Market.UAE,
        auto_confirm: bool = True,
    ) -> dict[str, Any]:
        session = await session_store.get(session_id) or {
            "channel": "agentic",
            "phone": phone,
            "market": market.value,
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "passengers": passengers,
        }
        await session_store.set(session_id, session)

        search_result = await execute_tool(
            session_id,
            "search_flights",
            {
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "passengers": passengers,
            },
            session,
        )
        offers = search_result.get("offers") or []
        if not offers:
            return {"status": "no_offers", "search": search_result}

        best = min(offers, key=lambda o: o.get("price", 999999))
        if not auto_confirm:
            return {"status": "offers_ready", "best_offer": best, "offers": offers[:3]}

        booking_result = await execute_tool(
            session_id,
            "create_booking",
            {"offer_id": best["offer_id"], "passengers": [{"type": "adult"}] * passengers},
            session,
        )
        if booking_result.get("error"):
            return {"status": "booking_failed", **booking_result}

        payment_result = await execute_tool(
            session_id,
            "send_payment_link",
            {"booking_id": booking_result.get("booking_id"), "phone": phone},
            session,
        )

        return {
            "status": "completed",
            "offer": best,
            "booking": booking_result,
            "payment": payment_result,
            "session_id": session_id,
        }

    async def create_session(self, phone: Optional[str] = None, market: Market = Market.UAE) -> str:
        session_id = f"agentic_{uuid4().hex[:12]}"
        await session_store.set(session_id, {"channel": "agentic", "phone": phone, "market": market.value})
        return session_id


agentic_booking = AgenticBookingService()
