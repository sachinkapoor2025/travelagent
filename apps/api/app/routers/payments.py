"""Stripe and Razorpay payment webhooks — DynamoDB."""

from uuid import UUID

from fastapi import APIRouter, Request

from app.storage.bookings_repo import booking_repo

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.json()
    if payload.get("type") == "checkout.session.completed":
        session = payload.get("data", {}).get("object", {})
        booking_id = session.get("metadata", {}).get("booking_id")
        if booking_id:
            await booking_repo.mark_paid(booking_id)
    return {"status": "ok"}


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request) -> dict:
    payload = await request.json()
    if payload.get("event") == "payment_link.paid":
        notes = payload.get("payload", {}).get("payment_link", {}).get("entity", {}).get("notes", {})
        booking_id = notes.get("booking_id")
        if booking_id:
            await booking_repo.mark_paid(booking_id, provider="razorpay")
    return {"status": "ok"}
