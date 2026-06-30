"""SMS channel via Twilio."""

from typing import Any

import httpx

from app.config import get_settings
from app.services.chat import chat_agent

settings = get_settings()


class SMSService:
    async def send(self, to: str, body: str) -> dict[str, Any]:
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            return {"mock": True, "to": to, "body": body}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={
                    "To": to,
                    "From": settings.twilio_phone_number_uae or settings.twilio_phone_number_india,
                    "Body": body,
                },
            )
            response.raise_for_status()
            return response.json()

    async def handle_incoming(self, from_number: str, body: str) -> str:
        result = await chat_agent.chat(message=body, session_id=f"sms_{from_number}", phone=from_number)
        reply = result["reply"]
        await self.send(from_number, reply[:1600])
        return reply


sms_service = SMSService()
