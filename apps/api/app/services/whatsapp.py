"""WhatsApp Business Cloud API integration."""

from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import get_settings
from app.models import LeadSource, Market
from app.services.compliance import detect_market_from_phone
from app.services.session import session_store

settings = get_settings()

WHATSAPP_SYSTEM_PROMPT = """You are Sarah, TravelAI's WhatsApp travel assistant for UAE and India customers.
Be warm, concise, and helpful. Use the customer's preferred language.

Flow: greet → ask language → collect origin, destination, dates, passengers → search flights →
present options → answer questions → create booking → send payment link.

Keep messages short (WhatsApp style). Use bullet points for flight options.
Never invent prices — say you'll search when you have origin, destination, and dates."""


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
            "text": {"body": text},
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
            f"✈️ Your TravelAI booking is ready!\n\n"
            f"Amount: {currency} {amount}\n"
            f"Pay securely here: {link}\n\n"
            f"We accept Visa, Mastercard, Amex, RuPay, UPI, and crypto cards."
        )
        return await self.send_text(to, message)

    async def process_incoming(self, from_number: str, text: str) -> str:
        session_id = f"wa_{from_number}"
        session = await session_store.get(session_id)
        market = detect_market_from_phone(from_number)

        if not session:
            session = {"phone": from_number, "market": market.value, "messages": []}
        session["messages"].append({"role": "user", "content": text})

        reply = await self._generate_reply(session, text, market)
        session["messages"].append({"role": "assistant", "content": reply})
        await session_store.set(session_id, session)

        if settings.whatsapp_access_token:
            await self.send_text(from_number, reply)

        return reply

    async def _generate_reply(self, session: dict[str, Any], text: str, market: Market) -> str:
        if not self.client:
            return self._fallback_reply(text, session, market)

        messages = [{"role": "system", "content": WHATSAPP_SYSTEM_PROMPT}]
        for msg in session.get("messages", [])[-10:]:
            messages.append(msg)

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content or "How can I help with your travel plans today?"

    def _fallback_reply(self, text: str, session: dict[str, Any], market: Market) -> str:
        lower = text.lower()
        if "language" in lower or "english" in lower or "hindi" in lower or "arabic" in lower:
            session["language"] = "hi" if "hindi" in lower else "ar" if "arabic" in lower else "en"
            return "Great! Where would you like to travel from and to?"

        if session.get("origin") is None and ("from" in lower or "dxb" in lower or "dubai" in lower):
            session["origin"] = "DXB" if "dubai" in lower or "dxb" in lower else text[:3].upper()
            return "And where would you like to go?"

        if session.get("destination") is None:
            session["destination"] = text[:3].upper() if len(text) <= 5 else text.split()[-1][:3].upper()
            return "When would you like to depart? (e.g. 2026-08-15)"

        currency = "AED" if market == Market.UAE else "INR"
        origin = session.get("origin", "DXB")
        dest = session.get("destination", "BOM")
        return (
            f"✈️ Top options {origin} → {dest}:\n"
            f"• Direct — {currency} {'1,299' if currency == 'AED' else '45,999'}\n"
            f"• 1-stop — {currency} {'1,065' if currency == 'AED' else '37,799'}\n"
            f"• Budget 2-stop — {currency} {'883' if currency == 'AED' else '31,279'}\n\n"
            f"Reply with 1, 2, or 3 to select, or ask me anything!"
        )


whatsapp_service = WhatsAppService()
