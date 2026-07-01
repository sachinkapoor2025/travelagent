"""Vapi voice agent — ElevenLabs Turbo + Deepgram multilingual STT."""

from typing import Any, Optional

import httpx

from app.config import get_settings
from app.models import CallDirection, Language, Market
from app.services.compliance import can_outbound_call, detect_market_from_phone, scrub_dnc
from app.services.session import session_store
from app.services.travel_tools import LANGUAGE_VOICES, TRANSCRIBER_LANG, execute_tool, openai_tool_definitions

settings = get_settings()

VOICE_PROMPTS = {
    "en": """You are Sarah, a warm female travel consultant at TravelAI for UAE and India.
Speak naturally in English. Use tools for search, booking, and payment links. Never invent prices.""",
    "ar": """أنتِ سارة، مستشارة سفر ودودة في TravelAI. تحدثي باللهجة الخليجية عندما يتحدث العميل بالعربية.
يمكنك التبديل إلى الإنجليزية عند الحاجة. استخدمي الأدوات للبحث والحجز.""",
    "hi": """आप Sarah हैं, TravelAI की travel consultant. हिंदी और Hinglish दोनों में बात करें।
Tools use करके flights search और booking करें। कीमतें guess न करें।""",
    "ur": """آپ Sarah ہیں، TravelAI کی travel consultant۔ اردو اور انگریزی دونوں میں بات کریں۔""",
}

VOICE_SYSTEM_PROMPT = VOICE_PROMPTS["en"]


def get_language_prompt(lang: str) -> str:
    return VOICE_PROMPTS.get(lang, VOICE_PROMPTS["en"])


def get_vapi_assistant_config(server_url: str, language: str = "en") -> dict[str, Any]:
    tool_defs = [t["function"] for t in openai_tool_definitions()]
    lang = language if language in LANGUAGE_VOICES else "en"
    first_messages = {
        "en": "Hello! Thank you for calling TravelAI. I'm Sarah, your travel assistant. How can I help you today?",
        "ar": "مرحباً! شكراً لاتصالك بTravelAI. أنا سارة، مساعدتك للسفر. كيف يمكنني مساعدتك؟",
        "hi": "Namaste! TravelAI par call karne ke liye dhanyavaad. Main Sarah hoon. Aapko kahan jaana hai?",
        "ur": "Assalam o alaikum! Main Sarah hoon, TravelAI se. Aap kahan travel karna chahte hain?",
    }
    return {
        "name": "TravelAI Sarah",
        "firstMessage": first_messages.get(lang, first_messages["en"]),
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.7,
            "systemPrompt": get_language_prompt(lang),
            "tools": [{"type": "function", "function": fn} for fn in tool_defs],
        },
        "voice": {
            "provider": "11labs",
            "voiceId": LANGUAGE_VOICES[lang],
            "model": "eleven_turbo_v2_5",
            "stability": 0.45,
            "similarityBoost": 0.75,
        },
        "transcriber": {
            "provider": "deepgram",
            "model": settings.deepgram_model,
            "language": TRANSCRIBER_LANG.get(lang, "multi"),
            "smartFormat": True,
        },
        "serverUrl": f"{server_url}/api/v1/voice/webhook",
        "serverMessages": ["tool-calls", "end-of-call-report", "status-update"],
        "endCallMessage": "Thank you for choosing TravelAI. Have a wonderful trip!",
        "recordingEnabled": True,
        "analysisPlan": {
            "summaryPlan": {"enabled": True},
            "structuredDataPlan": {"enabled": True},
        },
    }


async def handle_tool_call(session_id: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await execute_tool(session_id, tool_name, args)
    if tool_name == "set_language" and result.get("voice_id"):
        lang = args.get("language", "en")
        result["voice_override"] = {
            "voiceId": result["voice_id"],
            "transcriberLanguage": TRANSCRIBER_LANG.get(lang, "multi"),
            "systemPrompt": get_language_prompt(lang),
        }
    return result


async def initiate_outbound_call(phone: str, lead_data: dict[str, Any]) -> dict[str, Any]:
    on_dnc = lead_data.get("on_dnc", False)
    if not on_dnc:
        on_dnc = await scrub_dnc(phone)

    allowed, reason = can_outbound_call(
        phone,
        opt_in_voice=lead_data.get("opt_in_voice", False),
        on_dnc_list=on_dnc,
        whitelist=settings.twilio_whitelist,
    )
    if not allowed:
        return {"success": False, "reason": reason}

    market = detect_market_from_phone(phone)
    preferred_lang = lead_data.get("preferred_language", "en")
    session_id = f"call_{phone}_{lead_data.get('lead_id', 'new')}"
    await session_store.set(
        session_id,
        {
            "phone": phone,
            "market": market.value,
            "lead_id": str(lead_data.get("lead_id", "")),
            "language": preferred_lang,
            **{k: v for k, v in lead_data.items() if k not in {"lead_id", "on_dnc"}},
        },
    )

    if not settings.vapi_api_key:
        return {
            "success": True,
            "mock": True,
            "session_id": session_id,
            "language": preferred_lang,
            "message": f"Mock outbound call initiated to {phone} in {preferred_lang}",
        }

    payload = {
        "phoneNumberId": settings.vapi_phone_number_id,
        "customer": {"number": phone},
        "assistantId": settings.vapi_assistant_id,
        "assistantOverrides": {
            "variableValues": {"session_id": session_id, "market": market.value, "language": preferred_lang},
            "firstMessage": get_vapi_assistant_config("", preferred_lang)["firstMessage"],
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.vapi.ai/call/phone",
            headers={"Authorization": f"Bearer {settings.vapi_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        return {"success": True, "call": response.json(), "session_id": session_id, "language": preferred_lang}


def map_language(value: Optional[str]) -> Optional[Language]:
    if not value:
        return None
    mapping = {"en": Language.EN, "ar": Language.AR, "hi": Language.HI, "ur": Language.UR}
    return mapping.get(value.lower())
