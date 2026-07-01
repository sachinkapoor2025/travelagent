"""Bookings and payments repository — DynamoDB only."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.models import BookingStatus, PaymentProvider, PaymentStatus
from app.storage.dynamo import bookings_store, events_store, leads_store, now_iso


class BookingRepository:
    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        booking_id = str(uuid.uuid4())
        ts = now_iso()
        record = {
            "id": booking_id,
            "booking_id": booking_id,
            "lead_id": str(data["lead_id"]) if data.get("lead_id") else None,
            "duffel_order_id": data.get("duffel_order_id"),
            "pnr": data.get("pnr"),
            "status": data.get("status", BookingStatus.HELD.value),
            "origin": data["origin"],
            "destination": data["destination"],
            "departure_date": data["departure_date"],
            "return_date": data.get("return_date"),
            "passengers": data.get("passengers", 1),
            "total_amount": float(data.get("total_amount", 0)),
            "currency": data.get("currency", "AED"),
            "passenger_details": data.get("passenger_details"),
            "created_at": ts,
        }
        bookings_store().put(
            f"BOOKING#{booking_id}",
            "METADATA",
            record,
            gsi1pk="BOOKINGS",
            gsi1sk=ts,
        )
        return record

    async def get(self, booking_id: str) -> Optional[dict[str, Any]]:
        return bookings_store().get(f"BOOKING#{booking_id}", "METADATA")

    async def update_status(self, booking_id: str, status: str) -> None:
        bookings_store().update(f"BOOKING#{booking_id}", "METADATA", {"status": status, "updated_at": now_iso()})

    async def create_payment(self, booking_id: str, data: dict[str, Any]) -> dict[str, Any]:
        payment_id = str(uuid.uuid4())
        ts = now_iso()
        record = {
            "id": payment_id,
            "payment_id": payment_id,
            "booking_id": booking_id,
            "provider": data["provider"],
            "external_payment_id": data.get("external_payment_id"),
            "payment_link_url": data.get("payment_link_url"),
            "amount": float(data["amount"]),
            "currency": data["currency"],
            "status": data.get("status", PaymentStatus.PENDING.value),
            "metadata_json": data.get("metadata_json"),
            "created_at": ts,
        }
        bookings_store().put(f"BOOKING#{booking_id}", f"PAYMENT#{payment_id}", record)
        return record

    async def get_payments(self, booking_id: str) -> list[dict[str, Any]]:
        return bookings_store().query_pk(f"BOOKING#{booking_id}")

    async def mark_paid(self, booking_id: str, provider: Optional[str] = None) -> None:
        await self.update_status(booking_id, BookingStatus.CONFIRMED.value)
        for payment in await self.get_payments(booking_id):
            if payment.get("SK", "").startswith("PAYMENT#"):
                if provider is None or payment.get("provider") == provider:
                    bookings_store().update(
                        f"BOOKING#{booking_id}",
                        payment["SK"],
                        {"status": PaymentStatus.PAID.value},
                    )

    async def get_lead_phone(self, lead_id: Optional[str]) -> Optional[str]:
        if not lead_id:
            return None
        lead = leads_store().get(f"LEAD#{lead_id}", "METADATA")
        return lead.get("phone") if lead else None

    async def log_call(self, data: dict[str, Any]) -> dict[str, Any]:
        call_id = str(uuid.uuid4())
        record = {"call_id": call_id, **data, "created_at": now_iso()}
        events_store().put(f"CALL#{call_id}", "METADATA", record, gsi1pk="CALLS", gsi1sk=record["created_at"])
        return record

    async def save_campaign(self, data: dict[str, Any]) -> dict[str, Any]:
        campaign_id = str(uuid.uuid4())
        record = {"id": campaign_id, **data, "created_at": now_iso()}
        events_store().put(
            f"CAMPAIGN#{campaign_id}",
            "METADATA",
            record,
            gsi1pk="CAMPAIGNS",
            gsi1sk=record["created_at"],
        )
        return record

    async def list_campaigns(self, limit: int = 20) -> list[dict[str, Any]]:
        return events_store().query_gsi1("CAMPAIGNS", limit=limit)


booking_repo = BookingRepository()
