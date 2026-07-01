"""WhatsApp Business Cloud API — tool-calling AI assistant."""

import json
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import get_settings
from app.models import Market
from app.services.agent_router import classify_intent, specialist_prompt
from app.services.compliance import detect_market_from_phone
from app.services.personalization import format_prefs_for_prompt, load_preferences
from app.services.session import session_store
from app.services.travel_tools import execute_tool, openai_tool_definitions

settings = get_settings()

WHATSAPP_SYSTEM_PROMPT = """You are Sarah, TravelAI's WhatsApp travel assistant for UAE and India.
Use tools for flights, hotels, packages, bookings, and payment links. Never invent prices.
Keep messages short (WhatsApp style). Use bullet points for options."""


class WhatsAppService:
    def __init__(self) -> None:
        self.base_url = "https://graph.facebook.com/v21.0"
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def send_text(self, to: str, text: str) -> dict[str, Any]:
        if not settings.whatsapp_access_token:
            return {"mock": True, "to": to, "text": text}

        payload = {
            "messaging_product": "whatsapp",
            "to": to.replace("+", ""),
            "type": "text",
            "text": {"body": text[:4096]},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/{settings.whatsapp_phone_number_id}/messages",
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def send_payment_link(self, to: str, link: str, amount: str, currency: str) -> dict[str, Any]:
        message = (
            f"Your TravelAI booking is ready!\n\n"
            f"Amount: {currency} {amount}\n"
            f"Pay securely: {link}\n\n"
            f"Visa, Mastercard, Amex, RuPay, UPI accepted."
        )
        return await self.send_text(to, message)

    async def process_incoming(self, from_number: str, text: str) -> str:
        session_id = f"wa_{from_number}"
        session = await session_store.get(session_id)
        market = detect_market_from_phone(from_number)

        if not session:
            prefs = await load_preferences(from_number)
            session = {"phone": from_number, "market": market.value, "messages": [], **prefs}

        session["messages"].append({"role": "user", "content": text})
        agent_kind = classify_intent(text, session)
        reply = await self._generate_reply(session, session_id, agent_kind)
        session["messages"].append({"role": "assistant", "content": reply})
        await session_store.set(session_id, session)

        if settings.whatsapp_access_token:
            await self.send_text(from_number, reply)

        return reply

    async def _generate_reply(self, session: dict[str, Any], session_id: str, agent_kind: str) -> str:
        if not self.client:
            return await self._fallback_with_tools(session_id, session, session.get("messages", [])[-1]["content"])

        prefs_text = format_prefs_for_prompt(await load_preferences(session.get("phone")))
        system = f"{WHATSAPP_SYSTEM_PROMPT}\n{specialist_prompt(agent_kind)}\n{prefs_text}"
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for msg in session.get("messages", [])[-12]:
            messages.append(msg)

        tools = openai_tool_definitions()
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
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
                continue
            return choice.content or "How can I help with your travel plans today?"

        return "I found options — reply BOOK to proceed or ask for more details."

    async def _fallback_with_tools(self, session_id: str, session: dict[str, Any], text: str) -> str:
        lower = text.lower()
        if any(w in lower for w in ("search", "flight", "fly", "dxb", "bom")):
            origin = session.get("origin", "DXB")
            dest = session.get("destination", "BOM")
            result = await execute_tool(
                session_id,
                "search_flights",
                {"origin": origin, "destination": dest, "departure_date": session.get("departure_date", "2026-08-15")},
                session,
            )
            offers = result.get("offers", [])[:3]
            if offers:
                lines = [f"• {o.get('summary', 'Flight')} — {o.get('currency')} {o.get('price')}" for o in offers]
                return "Top flights:\n" + "\n".join(lines)
        return "Hi! I'm Sarah from TravelAI. Tell me where you'd like to fly from and to."


whatsapp_service = WhatsAppService()
