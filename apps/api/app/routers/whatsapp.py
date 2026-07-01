"""WhatsApp Cloud API webhooks."""

from app.routers.auth import admin_required
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import get_settings
from app.services.whatsapp import whatsapp_service

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
settings = get_settings()


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
) -> int:
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return int(hub_challenge or 0)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def whatsapp_webhook(request: Request) -> dict:
    payload = await request.json()

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                if msg.get("type") == "text":
                    from_number = msg.get("from", "")
                    text = msg.get("text", {}).get("body", "")
                    await whatsapp_service.process_incoming(f"+{from_number}", text)

    return {"status": "ok"}


@router.post("/send")
async def send_message(to: str, text: str, _admin: dict = Depends(admin_required())) -> dict:
    return await whatsapp_service.send_text(to, text)
