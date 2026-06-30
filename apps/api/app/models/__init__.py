"""SQLAlchemy models."""

import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Market(str, enum.Enum):
    UAE = "uae"
    INDIA = "india"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    QUOTED = "quoted"
    BOOKING = "booking"
    WON = "won"
    LOST = "lost"
    DNC = "dnc"


class LeadSource(str, enum.Enum):
    WEBSITE = "website"
    WHATSAPP = "whatsapp"
    VOICE_INBOUND = "voice_inbound"
    VOICE_OUTBOUND = "voice_outbound"
    GOOGLE_ADS = "google_ads"
    META_ADS = "meta_ads"
    REFERRAL = "referral"
    ABANDONED_SEARCH = "abandoned_search"
    PARTNER = "partner"


class CallDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    HELD = "held"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, enum.Enum):
    STRIPE = "stripe"
    RAZORPAY = "razorpay"


class Language(str, enum.Enum):
    EN = "en"
    AR = "ar"
    HI = "hi"
    UR = "ur"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    market: Mapped[Market] = mapped_column(Enum(Market), default=Market.UAE)
    source: Mapped[LeadSource] = mapped_column(Enum(LeadSource), default=LeadSource.WEBSITE)
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.NEW)
    score: Mapped[int] = mapped_column(Integer, default=0)
    preferred_language: Mapped[Optional[Language]] = mapped_column(Enum(Language), nullable=True)
    origin: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    destination: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    departure_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    return_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    passengers: Mapped[int] = mapped_column(Integer, default=1)
    cabin_class: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    budget_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trip_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    stop_preference: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    opt_in_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    opt_in_voice: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    calls: Mapped[List["Call"]] = relationship(back_populates="lead")
    bookings: Mapped[List["Booking"]] = relationship(back_populates="lead")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("leads.id"), nullable=True)
    external_call_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    direction: Mapped[CallDirection] = mapped_column(Enum(CallDirection))
    phone_from: Mapped[str] = mapped_column(String(20))
    phone_to: Mapped[str] = mapped_column(String(20))
    market: Mapped[Market] = mapped_column(Enum(Market))
    language: Mapped[Optional[Language]] = mapped_column(Enum(Language), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recording_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    session_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped[Optional["Lead"]] = relationship(back_populates="calls")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("leads.id"), nullable=True)
    duffel_order_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pnr: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.PENDING)
    origin: Mapped[str] = mapped_column(String(10))
    destination: Mapped[str] = mapped_column(String(10))
    departure_date: Mapped[str] = mapped_column(String(20))
    return_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    passengers: Mapped[int] = mapped_column(Integer, default=1)
    cabin_class: Mapped[str] = mapped_column(String(50), default="economy")
    total_amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    offer_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    passenger_details: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lead: Mapped[Optional["Lead"]] = relationship(back_populates="bookings")
    payments: Mapped[List["Payment"]] = relationship(back_populates="booking")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"))
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider))
    external_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_link_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    booking: Mapped["Booking"] = relationship(back_populates="payments")


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    route_origin: Mapped[str] = mapped_column(String(10))
    route_destination: Mapped[str] = mapped_column(String(10))
    market: Mapped[Market] = mapped_column(Enum(Market))
    platform: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    competitor_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    generated_ads: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    performance: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DncEntry(Base):
    __tablename__ = "dnc_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    market: Mapped[Market] = mapped_column(Enum(Market))
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
