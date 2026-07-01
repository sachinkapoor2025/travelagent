"""Flight search and booking — DynamoDB."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.models import BookingStatus, PaymentStatus
from app.schemas import BookingCreate, BookingResponse, FlightSearchRequest, FlightSearchResponse, PaymentLinkRequest, PaymentLinkResponse
from app.services.booking import duffel_client
from app.services.payments import create_payment_link
from app.storage.bookings_repo import booking_repo

router = APIRouter(prefix="/flights", tags=["flights"])


@router.post("/search", response_model=FlightSearchResponse)
async def search_flights(request: FlightSearchRequest, email: Optional[str] = None) -> FlightSearchResponse:
    from app.services.email_nurture import track_abandoned_search

    results = await duffel_client.search_flights(request)
    if email:
        track_abandoned_search(email, request.origin, request.destination, request.departure_date)
    return results


@router.post("/book", response_model=BookingResponse)
async def create_booking(payload: BookingCreate) -> BookingResponse:
    order = await duffel_client.create_order(payload.offer_id, payload.passengers)
    origin = payload.passengers[0].get("origin", "DXB") if payload.passengers else "DXB"
    destination = payload.passengers[0].get("destination", "BOM") if payload.passengers else "BOM"

    booking = await booking_repo.create(
        {
            "lead_id": str(payload.lead_id) if payload.lead_id else None,
            "duffel_order_id": order.get("id"),
            "pnr": order.get("booking_reference"),
            "status": "held",
            "origin": origin,
            "destination": destination,
            "departure_date": payload.passengers[0].get("departure_date", "2026-08-01") if payload.passengers else "2026-08-01",
            "passengers": len(payload.passengers),
            "total_amount": float(order.get("total_amount", 0)),
            "currency": order.get("total_currency", "AED"),
            "passenger_details": payload.passengers,
        }
    )
    return BookingResponse(
        id=booking["id"],
        status=BookingStatus(booking["status"]),
        origin=booking["origin"],
        destination=booking["destination"],
        departure_date=booking["departure_date"],
        total_amount=booking["total_amount"],
        currency=booking["currency"],
        pnr=booking.get("pnr"),
    )


@router.post("/payment-link", response_model=PaymentLinkResponse)
async def get_payment_link(payload: PaymentLinkRequest) -> PaymentLinkResponse:
    booking = await booking_repo.get(str(payload.booking_id))
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    phone = await booking_repo.get_lead_phone(booking.get("lead_id"))
    payment = await create_payment_link(booking, payload.market, phone)
    return PaymentLinkResponse(
        payment_id=payment["id"],
        payment_link_url=payment.get("payment_link_url") or "",
        provider=payment["provider"],
        amount=payment["amount"],
        currency=payment["currency"],
        status=PaymentStatus(payment["status"]),
    )


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: UUID) -> BookingResponse:
    booking = await booking_repo.get(str(booking_id))
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return BookingResponse(
        id=booking["id"],
        status=BookingStatus(booking["status"]),
        origin=booking["origin"],
        destination=booking["destination"],
        departure_date=booking["departure_date"],
        total_amount=booking["total_amount"],
        currency=booking["currency"],
        pnr=booking.get("pnr"),
    )
