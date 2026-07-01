"""Stripe and Razorpay payment integrations — DynamoDB."""

from typing import Any, Optional

import stripe

from app.config import get_settings
from app.models import Market, PaymentProvider, PaymentStatus
from app.storage.bookings_repo import booking_repo

settings = get_settings()


def _currency_for_market(market: Market) -> str:
    return "INR" if market == Market.INDIA else "AED"


async def create_payment_link(
    booking: dict[str, Any],
    market: Market,
    customer_phone: Optional[str] = None,
) -> dict[str, Any]:
    currency = _currency_for_market(market)
    amount = float(booking["total_amount"])
    booking_id = booking["id"]

    if market == Market.INDIA and settings.razorpay_key_id:
        return await _create_razorpay_link(booking_id, booking, amount, currency, customer_phone)
    return await _create_stripe_link(booking_id, booking, amount, currency, customer_phone)


async def _create_stripe_link(
    booking_id: str,
    booking: dict[str, Any],
    amount: float,
    currency: str,
    customer_phone: Optional[str],
) -> dict[str, Any]:
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
                            "name": f"Flight {booking['origin']} → {booking['destination']}",
                            "description": f"Travel booking ref {booking_id}",
                        },
                        "unit_amount": minor_units,
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{settings.site_url}/booking/{booking_id}/success",
            cancel_url=f"{settings.site_url}/booking/{booking_id}/cancel",
            metadata={"booking_id": booking_id},
        )
        link_url = session.url or ""
        external_id = session.id
    else:
        link_url = f"https://checkout.stripe.com/mock/{booking_id}"
        external_id = f"mock_stripe_{booking_id}"

    return await booking_repo.create_payment(
        booking_id,
        {
            "provider": PaymentProvider.STRIPE.value,
            "external_payment_id": external_id,
            "payment_link_url": link_url,
            "amount": amount,
            "currency": currency,
            "status": PaymentStatus.PENDING.value,
            "metadata_json": {"supports": ["visa", "mastercard", "amex", "apple_pay", "google_pay"]},
        },
    )


async def _create_razorpay_link(
    booking_id: str,
    booking: dict[str, Any],
    amount: float,
    currency: str,
    customer_phone: Optional[str],
) -> dict[str, Any]:
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        import razorpay

        client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
        payment_link = client.payment_link.create(
            {
                "amount": int(amount * 100),
                "currency": currency,
                "description": f"Flight {booking['origin']} to {booking['destination']}",
                "customer": {"contact": customer_phone or "+919999999999"},
                "notify": {"sms": True, "email": False},
                "notes": {"booking_id": booking_id},
            }
        )
        link_url = payment_link["short_url"]
        external_id = payment_link["id"]
    else:
        link_url = f"https://razorpay.com/mock/{booking_id}"
        external_id = f"mock_razorpay_{booking_id}"

    return await booking_repo.create_payment(
        booking_id,
        {
            "provider": PaymentProvider.RAZORPAY.value,
            "external_payment_id": external_id,
            "payment_link_url": link_url,
            "amount": amount,
            "currency": currency,
            "status": PaymentStatus.PENDING.value,
            "metadata_json": {"supports": ["visa", "mastercard", "rupay", "upi", "netbanking"]},
        },
    )
