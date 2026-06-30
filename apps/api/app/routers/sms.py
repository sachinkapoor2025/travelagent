"""SMS webhook via Twilio."""

from fastapi import APIRouter, Form

from app.services.sms import sms_service

router = APIRouter(prefix="/sms", tags=["sms"])


@router.post("/webhook")
async def sms_webhook(
    From: str = Form(...),
    Body: str = Form(...),
) -> str:
    await sms_service.handle_incoming(From, Body)
    return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
