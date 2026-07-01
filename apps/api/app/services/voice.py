"""Vapi voice agent — delegates tools to shared travel_tools."""

from typing import Any, Optional

import httpx

from app.config import get_settings
from app.models import CallDirection, Language, Market
from app.services.compliance import can_outbound_call, detect_market_from_phone
from app.services.session import session_store
from app.services.travel_tools import LANGUAGE_VOICES, TRANSCRIBER_LANG, execute_tool, openai_tool_definitions

settings = get_settings()

VOICE_SYSTEM_PROMPT = """You are Sarah, a warm travel consultant at TravelAI for UAE and India.
Speak naturally on phone calls. Use tools for search, booking, and payment links.
Never invent prices. Support English, Arabic, Hindi, and Urdu."""


def get_vapi_assistant_config(server_url: str) -> dict[str, Any]:
    tool_defs = [t["function"] for t in openai_tool_definitions()]
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
            "tools": [{"type": "function", "function": fn} for fn in tool_defs],
        },
        "voice": {
            "provider": "11labs",
            "voiceId": LANGUAGE_VOICES["en"],
            "model": "eleven_turbo_v2_5",
        },
        "transcriber": {"provider": "deepgram", "model": "nova-2", "language": "multi"},
        "serverUrl": f"{server_url}/api/v1/voice/webhook",
        "serverMessages": ["tool-calls", "end-of-call-report", "status-update"],
        "endCallMessage": "Thank you for choosing TravelAI. Have a wonderful trip!",
        "recordingEnabled": True,
    }


async def handle_tool_call(session_id: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await execute_tool(session_id, tool_name, args)
    if tool_name == "set_language" and result.get("voice_id"):
        result["voice_override"] = {
            "voiceId": result["voice_id"],
            "transcriberLanguage": result.get("transcriber_language", "multi"),
        }
    return result


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
