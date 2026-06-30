"""Stripe and Razorpay payment integrations."""

from typing import Optional
from uuid import UUID

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Booking, Market, Payment, PaymentProvider, PaymentStatus

settings = get_settings()


def _currency_for_market(market: Market) -> str:
    return "INR" if market == Market.INDIA else "AED"


async def create_payment_link(
    db: AsyncSession,
    booking: Booking,
    market: Market,
    customer_phone: Optional[str] = None,
) -> Payment:
    currency = _currency_for_market(market)
    amount = booking.total_amount

    if market == Market.INDIA and settings.razorpay_key_id:
        return await _create_razorpay_link(db, booking, amount, currency, customer_phone)
    return await _create_stripe_link(db, booking, amount, currency, customer_phone)


async def _create_stripe_link(
    db: AsyncSession,
    booking: Booking,
    amount: float,
    currency: str,
    customer_phone: Optional[str],
) -> Payment:
    if settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key
        minor_units = int(amount * 100) if currency != "JPY" else int(amount)
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": f"Flight {booking.origin} → {booking.destination}",
                            "description": f"Travel booking ref {booking.id}",
                        },
                        "unit_amount": minor_units,
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"https://your-domain.com/booking/{booking.id}/success",
            cancel_url=f"https://your-domain.com/booking/{booking.id}/cancel",
            metadata={"booking_id": str(booking.id)},
            phone_number_collection={"enabled": True} if customer_phone else None,
        )
        link_url = session.url or ""
        external_id = session.id
    else:
        link_url = f"https://checkout.stripe.com/mock/{booking.id}"
        external_id = f"mock_stripe_{booking.id}"

    payment = Payment(
        booking_id=booking.id,
        provider=PaymentProvider.STRIPE,
        external_payment_id=external_id,
        payment_link_url=link_url,
        amount=amount,
        currency=currency,
        status=PaymentStatus.PENDING,
        metadata_json={"supports": ["visa", "mastercard", "amex", "apple_pay", "google_pay"]},
    )
    db.add(payment)
    await db.flush()
    return payment


async def _create_razorpay_link(
    db: AsyncSession,
    booking: Booking,
    amount: float,
    currency: str,
    customer_phone: Optional[str],
) -> Payment:
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        import razorpay

        client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
        payment_link = client.payment_link.create(
            {
                "amount": int(amount * 100),
                "currency": currency,
                "description": f"Flight {booking.origin} to {booking.destination}",
                "customer": {"contact": customer_phone or "+919999999999"},
                "notify": {"sms": True, "email": False},
                "notes": {"booking_id": str(booking.id)},
            }
        )
        link_url = payment_link["short_url"]
        external_id = payment_link["id"]
    else:
        link_url = f"https://razorpay.com/mock/{booking.id}"
        external_id = f"mock_razorpay_{booking.id}"

    payment = Payment(
        booking_id=booking.id,
        provider=PaymentProvider.RAZORPAY,
        external_payment_id=external_id,
        payment_link_url=link_url,
        amount=amount,
        currency=currency,
        status=PaymentStatus.PENDING,
        metadata_json={"supports": ["visa", "mastercard", "rupay", "upi", "netbanking"]},
    )
    db.add(payment)
    await db.flush()
    return payment


async def handle_stripe_webhook(payload: dict) -> Optional[UUID]:
    event_type = payload.get("type")
    if event_type == "checkout.session.completed":
        metadata = payload.get("data", {}).get("object", {}).get("metadata", {})
        booking_id = metadata.get("booking_id")
        if booking_id:
            return UUID(booking_id)
    return None
