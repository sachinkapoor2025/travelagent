"""Stripe and Razorpay payment webhooks."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Booking, BookingStatus, Payment, PaymentStatus

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    payload = await request.json()
    event_type = payload.get("type")

    if event_type == "checkout.session.completed":
        session = payload.get("data", {}).get("object", {})
        booking_id = session.get("metadata", {}).get("booking_id")
        if booking_id:
            booking = await db.get(Booking, UUID(booking_id))
            if booking:
                booking.status = BookingStatus.CONFIRMED
                for payment in booking.payments:
                    payment.status = PaymentStatus.PAID

    return {"status": "ok"}


@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    payload = await request.json()
    event = payload.get("event")

    if event == "payment_link.paid":
        notes = payload.get("payload", {}).get("payment_link", {}).get("entity", {}).get("notes", {})
        booking_id = notes.get("booking_id")
        if booking_id:
            booking = await db.get(Booking, UUID(booking_id))
            if booking:
                booking.status = BookingStatus.CONFIRMED
                for payment in booking.payments:
                    if payment.provider.value == "razorpay":
                        payment.status = PaymentStatus.PAID

    return {"status": "ok"}
