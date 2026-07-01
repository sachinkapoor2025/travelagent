"""Web chat agent — tool-calling AI travel assistant."""

import json
import logging
from typing import Any, Optional
from uuid import uuid4

from openai import AsyncOpenAI

from app.config import get_settings
from app.models import Market
from app.services.agent_router import classify_intent, specialist_prompt
from app.services.compliance import detect_market_from_phone
from app.services.personalization import format_prefs_for_prompt, load_preferences
from app.services.session import session_store
from app.services.travel_tools import execute_tool, openai_tool_definitions
from app.storage.dynamo import events_store, now_iso

settings = get_settings()
logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """You are Sarah, TravelAI's expert travel consultant for UAE and India.
You help with flights, hotels, holiday packages, custom itineraries, visas, baggage rules,
airport transfers, stopovers, price alerts, referrals, and end-to-end booking.

Guidelines:
- Be warm, professional, and concise (2-4 sentences unless listing flight options).
- Support English, Arabic, Hindi, and Urdu — reply in the customer's language when possible.
- Use tools for live prices and bookings — never invent fares or availability.
- If origin, destination, or travel dates are missing, ask ONE clear follow-up question.
- Default assumptions when helpful: UAE customers often fly from DXB; India from BOM/DEL.
- Proactively suggest hotels, packages, or day plans when someone asks about a destination.
- For general travel advice (best time to visit, visa tips, packing), answer from your knowledge."""


class ChatAgentService:
    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None
        self._client_key: str = ""

    @property
    def client(self) -> Optional[AsyncOpenAI]:
        key = get_settings().openai_api_key
        if not key:
            self._client = None
            self._client_key = ""
            return None
        if self._client is None or key != self._client_key:
            self._client = AsyncOpenAI(api_key=key)
            self._client_key = key
        return self._client

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        phone: Optional[str] = None,
        referral_code: Optional[str] = None,
        email: Optional[str] = None,
    ) -> dict[str, Any]:
        session_id = session_id or f"chat_{uuid4().hex[:12]}"
        try:
            session = await session_store.get(session_id)

            if not session:
                market = detect_market_from_phone(phone) if phone else Market.UAE
                prefs = await load_preferences(phone)
                session = {
                    "channel": "web_chat",
                    "phone": phone,
                    "email": email,
                    "market": market.value,
                    "referral_code": referral_code,
                    "messages": [],
                    **prefs,
                }

            if email:
                session["email"] = email

            session["messages"].append({"role": "user", "content": message})
            agent_kind = classify_intent(message, session)
            reply, tool_data = await self._generate_reply(session, session_id, agent_kind)
            session["messages"].append({"role": "assistant", "content": reply})
            if tool_data:
                session["last_tool_data"] = tool_data
            try:
                await session_store.set(session_id, session)
            except Exception:
                logger.exception("Failed to persist chat session %s", session_id)

            try:
                self._track_event("chat_message", session_id, {"length": len(message), "agent": agent_kind})
            except Exception:
                logger.exception("Failed to track chat analytics event")

            return {
                "session_id": session_id,
                "reply": reply,
                "agent": agent_kind,
                "suggested_actions": self._suggested_actions(session),
                "tool_data": tool_data,
            }
        except Exception:
            logger.exception("Chat request failed for session %s", session_id)
            return {
                "session_id": session_id,
                "reply": "Sorry, I hit a brief glitch. Please tell me your origin, destination, and travel dates — I'll search flights for you.",
                "agent": "general",
                "suggested_actions": ["Search flights", "Hotels", "Packages"],
                "tool_data": None,
            }

    async def _generate_reply(self, session: dict[str, Any], session_id: str, agent_kind: str) -> tuple[str, Any]:
        if not self.client:
            return self._fallback(session), None

        try:
            prefs_text = format_prefs_for_prompt(await load_preferences(session.get("phone")))
            system = f"{CHAT_SYSTEM_PROMPT}\n{specialist_prompt(agent_kind)}\n{prefs_text}"
            messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
            for msg in session.get("messages", [])[-16]:
                messages.append({"role": msg["role"], "content": msg["content"]})

            tools = openai_tool_definitions()
            tool_data = None

            for _ in range(4):
                response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.6,
                    max_tokens=500,
                )
                choice = response.choices[0].message

                if choice.tool_calls:
                    assistant_msg: dict[str, Any] = {"role": "assistant", "content": choice.content or ""}
                    assistant_msg["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.function.name, "arguments": call.function.arguments or "{}"},
                        }
                        for call in choice.tool_calls
                    ]
                    messages.append(assistant_msg)
                    for call in choice.tool_calls:
                        args = json.loads(call.function.arguments or "{}")
                        try:
                            result = await execute_tool(session_id, call.function.name, args, session)
                        except Exception as tool_err:
                            logger.exception("Chat tool %s failed", call.function.name)
                            result = {"error": str(tool_err)}
                        session.update(await session_store.get(session_id) or {})
                        tool_data = result
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
                    continue

                return choice.content or "How can I help with your travel plans?", tool_data

            return "I found some options for you — would you like to book or adjust your search?", tool_data
        except Exception:
            logger.exception("OpenAI chat generation failed")
            return self._fallback(session), None

    def _fallback(self, session: dict[str, Any]) -> str:
        if session.get("last_search"):
            offers = session["last_search"][:3]
            lines = [f"• {o.get('summary', o.get('airline', 'Flight'))} — {o.get('currency')} {o.get('price')}" for o in offers]
            return "Top flights:\n" + "\n".join(lines) + "\n\nReply with an offer to book."
        msgs = session.get("messages", [])
        if len(msgs) <= 1:
            return "Hello! I'm Sarah from TravelAI. Which language do you prefer — English, Arabic, Hindi, or Urdu?"
        return "Tell me origin, destination, and dates — I'll search live flights for you."

    def _suggested_actions(self, session: dict[str, Any]) -> list[str]:
        actions = ["Search flights", "Hotels", "Packages", "Build itinerary", "Set price alert"]
        if session.get("last_search"):
            actions.insert(0, "Book selected flight")
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
