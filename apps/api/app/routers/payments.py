"""Stripe and Razorpay payment webhooks — DynamoDB."""

import hashlib
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import get_settings
from app.storage.bookings_repo import booking_repo

router = APIRouter(prefix="/payments", tags=["payments"])
settings = get_settings()
logger = logging.getLogger("travel-ai-payments")


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> dict:
    payload_bytes = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if settings.stripe_webhook_secret and sig:
        if not _verify_stripe_signature(payload_bytes, sig, settings.stripe_webhook_secret):
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    import json

    payload = json.loads(payload_bytes)
    if payload.get("type") == "checkout.session.completed":
        session = payload.get("data", {}).get("object", {})
        booking_id = session.get("metadata", {}).get("booking_id")
        if booking_id:
            await booking_repo.mark_paid(booking_id)
    return {"status": "ok"}


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request) -> dict:
    payload_bytes = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")

    if settings.razorpay_webhook_secret and sig:
        expected = hmac.new(
            settings.razorpay_webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=400, detail="Invalid Razorpay signature")

    import json

    payload = json.loads(payload_bytes)
    if payload.get("event") == "payment_link.paid":
        notes = payload.get("payload", {}).get("payment_link", {}).get("entity", {}).get("notes", {})
        booking_id = notes.get("booking_id")
        if booking_id:
            await booking_repo.mark_paid(booking_id, provider="razorpay")
    return {"status": "ok"}


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    try:
        import stripe

        stripe.Webhook.construct_event(payload, sig_header, secret)
        return True
    except Exception:
        logger.warning("Stripe webhook signature verification failed")
        return False
