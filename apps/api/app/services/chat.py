"""Web chat agent — embeddable AI travel assistant."""

from typing import Any, Optional
from uuid import uuid4

from openai import AsyncOpenAI

from app.config import get_settings
from app.models import LeadSource, Market
from app.services.compliance import detect_market_from_phone
from app.services.session import session_store
from app.storage.dynamo import events_store, now_iso

settings = get_settings()

CHAT_SYSTEM_PROMPT = """You are Sarah, TravelAI's web chat travel assistant for UAE and India.
Be warm, concise, and helpful. Support English, Arabic, Hindi, and Urdu.

Guide users through: language → origin/destination → dates → passengers → flight preferences →
search results → booking → payment link.

Keep responses short (2-4 sentences). Use bullet points for flight options.
Never invent prices. If you have origin, destination, and dates, tell the user you're searching.
Offer hotels and package deals when relevant. Mention price alerts if user is browsing."""


class ChatAgentService:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        phone: Optional[str] = None,
        referral_code: Optional[str] = None,
    ) -> dict[str, Any]:
        session_id = session_id or f"chat_{uuid4().hex[:12]}"
        session = await session_store.get(session_id)

        if not session:
            market = detect_market_from_phone(phone) if phone else Market.UAE
            session = {
                "channel": "web_chat",
                "phone": phone,
                "market": market.value,
                "referral_code": referral_code,
                "messages": [],
            }

        session["messages"].append({"role": "user", "content": message})
        reply = await self._generate_reply(session)
        session["messages"].append({"role": "assistant", "content": reply})
        await session_store.set(session_id, session)

        self._track_event("chat_message", session_id, {"length": len(message)})

        return {
            "session_id": session_id,
            "reply": reply,
            "suggested_actions": self._suggested_actions(session),
        }

    async def _generate_reply(self, session: dict[str, Any]) -> str:
        if not self.client:
            return self._fallback(session)

        messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
        for msg in session.get("messages", [])[-20:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=400,
        )
        return response.choices[0].message.content or "How can I help with your travel plans?"

    def _fallback(self, session: dict[str, Any]) -> str:
        msgs = session.get("messages", [])
        if len(msgs) <= 1:
            return (
                "Hello! I'm Sarah from TravelAI ✈️ Which language do you prefer — "
                "English, Arabic, Hindi, or Urdu?"
            )
        return (
            "Thanks! Tell me your origin city, destination, travel dates, and number of passengers — "
            "I'll find the best flights for you."
        )

    def _suggested_actions(self, session: dict[str, Any]) -> list[str]:
        actions = ["Search flights", "Hotels", "Build itinerary", "Set price alert"]
        if session.get("phone"):
            actions.append("Get AI phone callback")
        return actions

    def _track_event(self, event_type: str, session_id: str, meta: dict[str, Any]) -> None:
        store = events_store()
        if not store.enabled:
            return
        ts = now_iso()
        store.put(
            f"EVENT#{event_type}",
            ts,
            {"event_type": event_type, "session_id": session_id, **meta},
            gsi1pk="ANALYTICS",
            gsi1sk=ts,
        )


chat_agent = ChatAgentService()
