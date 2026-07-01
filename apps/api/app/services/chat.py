"""Web chat agent — tool-calling AI travel assistant."""

import json
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

CHAT_SYSTEM_PROMPT = """You are Sarah, TravelAI's web chat travel assistant for UAE and India.
Be warm, concise, and helpful. Support English, Arabic, Hindi, and Urdu.

Always use tools to search flights, hotels, packages, create bookings, and send payment links.
Never invent prices — call search_flights first. Keep responses short (2-4 sentences)."""


class ChatAgentService:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        phone: Optional[str] = None,
        referral_code: Optional[str] = None,
        email: Optional[str] = None,
    ) -> dict[str, Any]:
        session_id = session_id or f"chat_{uuid4().hex[:12]}"
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
        await session_store.set(session_id, session)

        self._track_event("chat_message", session_id, {"length": len(message), "agent": agent_kind})

        return {
            "session_id": session_id,
            "reply": reply,
            "agent": agent_kind,
            "suggested_actions": self._suggested_actions(session),
            "tool_data": tool_data,
        }

    async def _generate_reply(self, session: dict[str, Any], session_id: str, agent_kind: str) -> tuple[str, Any]:
        if not self.client:
            return self._fallback(session), None

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
                messages.append(choice.model_dump(exclude_none=True))
                for call in choice.tool_calls:
                    args = json.loads(call.function.arguments or "{}")
                    result = await execute_tool(session_id, call.function.name, args, session)
                    session.update(await session_store.get(session_id) or {})
                    tool_data = result
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
                continue

            return choice.content or "How can I help with your travel plans?", tool_data

        return "I found some options for you — would you like to book or adjust your search?", tool_data

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
