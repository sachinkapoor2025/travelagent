"""Shared travel tool handlers — voice, chat, WhatsApp."""

from typing import Any, Optional

from app.models import Market
from app.schemas import FlightSearchRequest, HotelSearchRequest, ItineraryCreate, PackageSearchRequest
from app.services.booking import duffel_client
from app.services.hotels import hotel_service
from app.services.itinerary import itinerary_service
from app.services.payments import create_payment_link
from app.services.personalization import save_preferences
from app.services.session import session_store
from app.storage.bookings_repo import booking_repo

LANGUAGE_VOICES = {
    "en": "21m00Tcm4TlvDq8ikWAM",
    "ar": "VR6AewLTigWG4xSOukaG",
    "hi": "pNInz6obpgDQGcFmaJgB",
    "ur": "pNInz6obpgDQGcFmaJgB",
}

TRANSCRIBER_LANG = {"en": "en", "ar": "ar", "hi": "hi", "ur": "ur"}


def openai_tool_definitions() -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "set_language", "description": "Store customer language", "parameters": {"type": "object", "properties": {"language": {"type": "string", "enum": ["en", "ar", "hi", "ur"]}}, "required": ["language"]}}},
        {"type": "function", "function": {"name": "update_travel_details", "description": "Save origin, destination, dates, passengers, cabin, stop preference", "parameters": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "departure_date": {"type": "string"}, "return_date": {"type": "string"}, "passengers": {"type": "integer"}, "cabin_class": {"type": "string"}, "stop_preference": {"type": "string"}, "home_airport": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "search_flights", "description": "Search live flight offers", "parameters": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "departure_date": {"type": "string"}, "return_date": {"type": "string"}, "passengers": {"type": "integer"}, "cabin_class": {"type": "string"}, "max_stops": {"type": "integer"}, "email": {"type": "string"}}, "required": ["origin", "destination", "departure_date"]}}},
        {"type": "function", "function": {"name": "search_hotels", "description": "Search hotels at destination", "parameters": {"type": "object", "properties": {"city_code": {"type": "string"}, "check_in": {"type": "string"}, "check_out": {"type": "string"}, "guests": {"type": "integer"}}, "required": ["city_code", "check_in", "check_out"]}}},
        {"type": "function", "function": {"name": "search_packages", "description": "Search holiday packages", "parameters": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "market": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "create_booking", "description": "Book selected flight offer", "parameters": {"type": "object", "properties": {"offer_id": {"type": "string"}, "passengers": {"type": "array", "items": {"type": "object"}}}, "required": ["offer_id"]}}},
        {"type": "function", "function": {"name": "send_payment_link", "description": "Send Stripe/Razorpay payment link", "parameters": {"type": "object", "properties": {"booking_id": {"type": "string"}, "phone": {"type": "string"}}, "required": ["booking_id"]}}},
        {"type": "function", "function": {"name": "build_itinerary", "description": "Generate AI day-by-day itinerary", "parameters": {"type": "object", "properties": {"destination": {"type": "string"}, "origin": {"type": "string"}, "days": {"type": "integer"}, "budget": {"type": "number"}, "interests": {"type": "string"}}, "required": ["destination", "days"]}}},
        {"type": "function", "function": {"name": "save_traveler_preferences", "description": "Persist preferences for future personalization", "parameters": {"type": "object", "properties": {"phone": {"type": "string"}, "origin": {"type": "string"}, "destination": {"type": "string"}, "cabin_class": {"type": "string"}, "stop_preference": {"type": "string"}, "preferred_language": {"type": "string"}}, "required": ["phone"]}}},
    ]


async def execute_tool(session_id: str, tool_name: str, args: dict[str, Any], session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    session = session or await session_store.get(session_id) or {}
    market = Market(session.get("market", "uae"))

    if tool_name == "set_language":
        lang = args.get("language", "en")
        session = await session_store.update(session_id, {"language": lang, "voice_id": LANGUAGE_VOICES.get(lang)})
        return {"result": f"Language set to {lang}", "voice_id": LANGUAGE_VOICES.get(lang), "transcriber_language": TRANSCRIBER_LANG.get(lang, "multi")}

    if tool_name == "update_travel_details":
        session = await session_store.update(session_id, {k: v for k, v in args.items() if v is not None})
        phone = session.get("phone")
        if phone:
            await save_preferences(phone, args)
        return {"result": "Travel details saved", "session": {k: session.get(k) for k in args}}

    if tool_name == "search_flights":
        from app.services.email_nurture import track_abandoned_search

        max_stops = args.get("max_stops")
        stop_pref = session.get("stop_preference") or args.get("stop_preference")
        if stop_pref == "direct":
            max_stops = 0
        elif stop_pref == "1-stop":
            max_stops = 1

        search = FlightSearchRequest(
            origin=args.get("origin", session.get("origin", "DXB")),
            destination=args.get("destination", session.get("destination", "BOM")),
            departure_date=args.get("departure_date", session.get("departure_date", "2026-08-01")),
            return_date=args.get("return_date", session.get("return_date")),
            passengers=args.get("passengers", session.get("passengers", 1)),
            cabin_class=args.get("cabin_class", session.get("cabin_class", "economy")),
            max_stops=max_stops,
            market=market,
        )
        results = await duffel_client.search_flights(search)
        await session_store.update(
            session_id,
            {
                "origin": search.origin,
                "destination": search.destination,
                "departure_date": search.departure_date,
                "last_search": [o.model_dump() for o in results.offers],
            },
        )
        email = args.get("email") or session.get("email")
        if email:
            track_abandoned_search(email, search.origin, search.destination, search.departure_date)
        return {"result": "Found flights", "offers": [o.model_dump() for o in results.offers[:5]]}

    if tool_name == "search_hotels":
        req = HotelSearchRequest(
            city=args.get("city_code", args.get("city", session.get("destination", "DXB"))),
            check_in=args.get("check_in", session.get("departure_date", "2026-08-01")),
            check_out=args.get("check_out", session.get("return_date", "2026-08-05")),
            guests=args.get("guests", session.get("passengers", 2)),
            market=market,
        )
        hotels = await hotel_service.search_hotels(req)
        return {"result": "Found hotels", "hotels": [h.model_dump() for h in hotels[:5]]}

    if tool_name == "search_packages":
        req = PackageSearchRequest(
            origin=args.get("origin", session.get("origin")),
            destination=args.get("destination", session.get("destination")),
            market=market,
        )
        packages = await hotel_service.search_packages(req)
        return {"result": "Found packages", "packages": [p.model_dump() for p in packages[:5]]}

    if tool_name == "create_booking":
        offer_id = args["offer_id"]
        passengers = args.get("passengers") or [{"type": "adult"}]
        order = await duffel_client.create_order(offer_id, passengers)
        booking = await booking_repo.create(
            {
                "lead_id": session.get("lead_id"),
                "duffel_order_id": order.get("id"),
                "pnr": order.get("booking_reference"),
                "status": "held",
                "origin": session.get("origin", "DXB"),
                "destination": session.get("destination", "BOM"),
                "departure_date": session.get("departure_date", "2026-08-01"),
                "passengers": len(passengers),
                "total_amount": float(order.get("total_amount", 0)),
                "currency": order.get("total_currency", "AED"),
                "passenger_details": passengers,
            }
        )
        booking_data = {"booking_id": booking["id"], "pnr": booking.get("pnr"), "amount": booking["total_amount"], "currency": booking["currency"]}
        await session_store.update(session_id, {"booking": booking_data})
        return {"result": "Booking created", **booking_data}

    if tool_name == "send_payment_link":
        booking_id = args.get("booking_id") or session.get("booking", {}).get("booking_id")
        phone = args.get("phone") or session.get("phone")
        if not booking_id:
            return {"error": "No booking_id — create booking first"}
        booking = await booking_repo.get(str(booking_id))
        if not booking:
            return {"error": "Booking not found"}
        payment = await create_payment_link(booking, market, phone)
        link = payment.get("payment_link_url") or ""
        if phone and link:
            from app.services.whatsapp import whatsapp_service

            await whatsapp_service.send_payment_link(phone, link, str(booking["total_amount"]), booking.get("currency", "AED"))
        return {
            "result": "Payment link created",
            "payment_link": link,
            "provider": payment.get("provider"),
            "accepted_methods": "Visa, Mastercard, Amex, RuPay, UPI, Apple Pay, Google Pay",
        }

    if tool_name == "build_itinerary":
        req = ItineraryCreate(
            destination=args.get("destination", session.get("destination", "DXB")),
            origin=args.get("origin", session.get("origin")),
            days=int(args.get("days", 5)),
            budget=args.get("budget"),
            interests=args.get("interests", "culture, food"),
            travelers=int(session.get("passengers", 2)),
            market=market,
        )
        itinerary = await itinerary_service.create(req)
        return {"result": "Itinerary ready", "itinerary": itinerary.model_dump()}

    if tool_name == "save_traveler_preferences":
        phone = args.get("phone") or session.get("phone")
        if not phone:
            return {"error": "Phone required to save preferences"}
        saved = await save_preferences(phone, args)
        return {"result": "Preferences saved", "preferences": saved}

    return {"error": f"Unknown tool: {tool_name}"}
