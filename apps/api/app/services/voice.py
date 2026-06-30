"""Vapi voice agent orchestration and tool handlers."""

from typing import Any

import httpx

from app.config import get_settings
from typing import Optional

from app.models import CallDirection, Language, Market
from app.schemas import FlightSearchRequest
from app.services.booking import duffel_client
from app.services.compliance import can_outbound_call, detect_market_from_phone
from app.services.session import session_store

settings = get_settings()

VOICE_SYSTEM_PROMPT = """You are Sarah, a warm and professional travel consultant at TravelAI.
You speak naturally like a real human — never robotic. Use short sentences, occasional filler words,
and empathetic tone. You help customers book flights for UAE and India markets.

CONVERSATION FLOW (follow in order, skip steps already completed):
1. Greet warmly and ask preferred language: English, Arabic, Hindi, or Urdu
2. Ask travel FROM city/airport and TO destination
3. Ask departure date and return date (if round trip)
4. Ask flight preference: direct, 1-stop, or multi-stop (cheapest)
5. Ask number of passengers and cabin class (economy/business)
6. Search flights and present top 3 options clearly with prices
7. Answer any questions about baggage, visa, cancellation, layovers
8. Confirm selected option and collect passenger details
9. Create booking and send secure payment link (accepts Amex, Mastercard, RuPay, UPI, crypto cards)
10. Confirm booking reference after payment

RULES:
- Always use the language the customer chose throughout the call
- Never invent prices — always call search_flights tool first
- If unsure, ask clarifying questions
- Be concise — this is a phone call, not an essay
- Disclose you are an AI travel assistant from TravelAI if asked
- For Arabic: use polite formal tone. For Hindi/Hinglish: natural conversational style.

Current session context is provided in each tool call."""


def get_vapi_assistant_config(server_url: str) -> dict[str, Any]:
    return {
        "name": "TravelAI Sarah",
        "firstMessage": (
            "Hello! Thank you for calling TravelAI. My name is Sarah, your travel assistant. "
            "Which language would you prefer — English, Arabic, Hindi, or Urdu?"
        ),
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.7,
            "systemPrompt": VOICE_SYSTEM_PROMPT,
            "tools": [
                {"type": "function", "function": {"name": "set_language", "description": "Store customer language preference", "parameters": {"type": "object", "properties": {"language": {"type": "string", "enum": ["en", "ar", "hi", "ur"]}}, "required": ["language"]}}},
                {"type": "function", "function": {"name": "update_travel_details", "description": "Store travel search parameters", "parameters": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "departure_date": {"type": "string"}, "return_date": {"type": "string"}, "passengers": {"type": "integer"}, "cabin_class": {"type": "string"}, "stop_preference": {"type": "string", "enum": ["direct", "1-stop", "multi-stop", "cheapest"]}}, "required": ["origin", "destination"]}}},
                {"type": "function", "function": {"name": "search_flights", "description": "Search available flights", "parameters": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "departure_date": {"type": "string"}, "return_date": {"type": "string"}, "passengers": {"type": "integer"}, "cabin_class": {"type": "string"}, "max_stops": {"type": "integer"}}, "required": ["origin", "destination", "departure_date"]}}},
                {"type": "function", "function": {"name": "create_booking", "description": "Create flight booking for selected offer", "parameters": {"type": "object", "properties": {"offer_id": {"type": "string"}, "passengers": {"type": "array", "items": {"type": "object"}}}, "required": ["offer_id", "passengers"]}}},
                {"type": "function", "function": {"name": "send_payment_link", "description": "Send payment link via SMS/WhatsApp", "parameters": {"type": "object", "properties": {"booking_id": {"type": "string"}, "phone": {"type": "string"}}, "required": ["booking_id", "phone"]}}},
            ],
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "21m00Tcm4TlvDq8ikWAM",
            "model": "eleven_turbo_v2_5",
        },
        "transcriber": {"provider": "deepgram", "model": "nova-2", "language": "multi"},
        "serverUrl": f"{server_url}/api/v1/voice/webhook",
        "serverMessages": ["tool-calls", "end-of-call-report", "status-update"],
        "endCallMessage": "Thank you for choosing TravelAI. Have a wonderful trip!",
        "recordingEnabled": True,
    }


async def handle_tool_call(session_id: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    session = await session_store.get(session_id)

    if tool_name == "set_language":
        lang = args.get("language", "en")
        session = await session_store.update(session_id, {"language": lang})
        return {"result": f"Language set to {lang}", "session": session}

    if tool_name == "update_travel_details":
        session = await session_store.update(session_id, args)
        return {"result": "Travel details saved", "session": session}

    if tool_name == "search_flights":
        market = Market(session.get("market", "uae"))
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
        await session_store.update(session_id, {"last_search": [o.model_dump() for o in results.offers]})
        return {
            "result": "Found flights",
            "offers": [o.model_dump() for o in results.offers],
            "instruction": "Present these options naturally to the customer. Mention airline, stops, price.",
        }

    if tool_name == "create_booking":
        offer_id = args["offer_id"]
        passengers = args.get("passengers", [])
        order = await duffel_client.create_order(offer_id, passengers)
        booking_data = {
            "booking_id": order.get("id"),
            "pnr": order.get("booking_reference"),
            "amount": order.get("total_amount"),
            "currency": order.get("total_currency"),
        }
        await session_store.update(session_id, {"booking": booking_data})
        return {"result": "Booking created", **booking_data}

    if tool_name == "send_payment_link":
        booking_id = args.get("booking_id", session.get("booking", {}).get("booking_id"))
        phone = args.get("phone", session.get("phone"))
        return {
            "result": "Payment link sent",
            "payment_link": f"https://pay.travelai.com/{booking_id}",
            "phone": phone,
            "accepted_methods": "Visa, Mastercard, Amex, RuPay, UPI, Apple Pay, Google Pay, crypto cards",
        }

    return {"result": f"Unknown tool: {tool_name}"}


async def initiate_outbound_call(phone: str, lead_data: dict[str, Any]) -> dict[str, Any]:
    allowed, reason = can_outbound_call(
        phone,
        opt_in_voice=lead_data.get("opt_in_voice", False),
        on_dnc_list=lead_data.get("on_dnc", False),
        whitelist=settings.twilio_whitelist,
    )
    if not allowed:
        return {"success": False, "reason": reason}

    market = detect_market_from_phone(phone)
    session_id = f"call_{phone}_{lead_data.get('lead_id', 'new')}"
    await session_store.set(
        session_id,
        {
            "phone": phone,
            "market": market.value,
            "lead_id": str(lead_data.get("lead_id", "")),
            **{k: v for k, v in lead_data.items() if k not in {"lead_id", "on_dnc"}},
        },
    )

    if not settings.vapi_api_key:
        return {
            "success": True,
            "mock": True,
            "session_id": session_id,
            "message": f"Mock outbound call initiated to {phone}",
        }

    payload = {
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {"number": phone},
        "assistantId": settings.vapi_assistant_id,
        "assistantOverrides": {
            "variableValues": {"session_id": session_id, "market": market.value},
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.vapi.ai/call/phone",
            headers={"Authorization": f"Bearer {settings.vapi_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        return {"success": True, "call": response.json(), "session_id": session_id}


def map_language(value: Optional[str]) -> Optional[Language]:
    if not value:
        return None
    mapping = {"en": Language.EN, "ar": Language.AR, "hi": Language.HI, "ur": Language.UR}
    return mapping.get(value.lower())
