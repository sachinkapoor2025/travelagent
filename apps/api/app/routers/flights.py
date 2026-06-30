"""Flight search and booking endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Booking, BookingStatus, Lead
from app.schemas import BookingCreate, BookingResponse, FlightSearchRequest, FlightSearchResponse, PaymentLinkRequest, PaymentLinkResponse
from app.services.booking import duffel_client
from app.services.payments import create_payment_link

router = APIRouter(prefix="/flights", tags=["flights"])


@router.post("/search", response_model=FlightSearchResponse)
async def search_flights(request: FlightSearchRequest) -> FlightSearchResponse:
    return await duffel_client.search_flights(request)


@router.post("/book", response_model=BookingResponse)
async def create_booking(payload: BookingCreate, db: AsyncSession = Depends(get_db)) -> Booking:
    order = await duffel_client.create_order(payload.offer_id, payload.passengers)

    origin = payload.passengers[0].get("origin", "DXB") if payload.passengers else "DXB"
    destination = payload.passengers[0].get("destination", "BOM") if payload.passengers else "BOM"

    booking = Booking(
        lead_id=payload.lead_id,
        duffel_order_id=order.get("id"),
        pnr=order.get("booking_reference"),
        status=BookingStatus.HELD,
        origin=origin,
        destination=destination,
        departure_date=payload.passengers[0].get("departure_date", "2026-08-01") if payload.passengers else "2026-08-01",
        passengers=len(payload.passengers),
        total_amount=float(order.get("total_amount", 0)),
        currency=order.get("total_currency", "AED"),
        passenger_details=payload.passengers,
    )
    db.add(booking)
    await db.flush()
    return booking


@router.post("/payment-link", response_model=PaymentLinkResponse)
async def get_payment_link(payload: PaymentLinkRequest, db: AsyncSession = Depends(get_db)) -> PaymentLinkResponse:
    booking = await db.get(Booking, payload.booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    phone = None
    if booking.lead_id:
        lead = await db.get(Lead, booking.lead_id)
        phone = lead.phone if lead else None

    payment = await create_payment_link(db, booking, payload.market, phone)
    return PaymentLinkResponse(
        payment_id=payment.id,
        payment_link_url=payment.payment_link_url or "",
        provider=payment.provider.value,
        amount=payment.amount,
        currency=payment.currency,
        status=payment.status,
    )


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: UUID, db: AsyncSession = Depends(get_db)) -> Booking:
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking
