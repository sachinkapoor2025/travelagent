"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import BookingStatus, Language, LeadSource, LeadStatus, Market, PaymentStatus


class LeadCreate(BaseModel):
    phone: str
    email: Optional[str] = None
    name: Optional[str] = None
    market: Market = Market.UAE
    source: LeadSource = LeadSource.WEBSITE
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    passengers: int = 1
    cabin_class: Optional[str] = None
    budget_max: Optional[float] = None
    stop_preference: Optional[str] = None
    preferred_language: Optional[Language] = None
    opt_in_marketing: bool = False
    opt_in_voice: bool = False
    metadata: Optional[Dict[str, Any]] = None


class LeadResponse(BaseModel):
    id: UUID
    phone: str
    email: Optional[str] = None
    name: Optional[str] = None
    market: Market
    source: LeadSource
    status: LeadStatus
    score: int
    temperature: Optional[str] = None
    preferred_language: Optional[Language] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    passengers: int = 1
    cabin_class: Optional[str] = None
    budget_max: Optional[float] = None
    stop_preference: Optional[str] = None
    location: Optional[str] = None
    source_detail: Optional[str] = None
    source_label: Optional[str] = None
    travel_intent: Optional[str] = None
    notes: Optional[str] = None
    enrichment: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FlightSearchRequest(BaseModel):
    origin: str = Field(..., min_length=3, max_length=3, description="IATA airport code")
    destination: str = Field(..., min_length=3, max_length=3)
    departure_date: str
    return_date: Optional[str] = None
    passengers: int = Field(1, ge=1, le=9)
    cabin_class: str = "economy"
    max_stops: Optional[int] = None
    market: Market = Market.UAE


class FlightOffer(BaseModel):
    offer_id: str
    airline: str
    flight_number: str
    origin: str
    destination: str
    departure_at: str
    arrival_at: str
    duration: str
    stops: int
    price: float
    currency: str
    cabin_class: str
    summary: str


class FlightSearchResponse(BaseModel):
    offers: List[FlightOffer]
    search_id: Optional[str] = None


class BookingCreate(BaseModel):
    lead_id: Optional[UUID] = None
    offer_id: str
    passengers: List[Dict[str, Any]]
    market: Market = Market.UAE


class BookingResponse(BaseModel):
    id: UUID
    status: BookingStatus
    origin: str
    destination: str
    departure_date: str
    total_amount: float
    currency: str
    pnr: Optional[str]

    model_config = {"from_attributes": True}


class PaymentLinkRequest(BaseModel):
    booking_id: UUID
    market: Market = Market.UAE


class PaymentLinkResponse(BaseModel):
    payment_id: UUID
    payment_link_url: str
    provider: str
    amount: float
    currency: str
    status: PaymentStatus


class AdAnalysisRequest(BaseModel):
    origin: str
    destination: str
    market: Market = Market.UAE
    platform: str = "google"


class AdVariant(BaseModel):
    headline: str
    description: str
    cta: str
    predicted_ctr_score: float
    rationale: str


class GeneratedAdPackage(BaseModel):
    hook: str
    body_copy: str
    offer_usp: str
    cta: str
    target_persona: str
    visual_description: str
    headline_ar: str = ""
    headline_hi: str = ""
    cta_ar: str = ""
    cta_hi: str = ""


class AdAnalysisResponse(BaseModel):
    route: str
    market: Market
    competitor_insights: List[str]
    winning_patterns: List[str]
    ad_variants: List[AdVariant]
    gap_analysis: List[str] = []
    competitor_ads: List[Dict[str, Any]] = []
    generated_package: Optional[GeneratedAdPackage] = None


class WhatsAppWebhookMessage(BaseModel):
    from_number: str
    message_id: str
    text: str
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    openai_configured: bool = False


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    referral_code: Optional[str] = None


class ChatMessageResponse(BaseModel):
    session_id: str
    reply: str
    suggested_actions: List[str] = []
    agent: Optional[str] = None
    tool_data: Optional[Dict[str, Any]] = None


class HotelSearchRequest(BaseModel):
    city: str
    check_in: str
    check_out: str
    guests: int = Field(2, ge=1, le=10)
    rooms: int = Field(1, ge=1, le=5)
    market: Market = Market.UAE
    limit: int = Field(5, ge=1, le=20)

    @property
    def nights(self) -> int:
        return max(1, 3)


class HotelOffer(BaseModel):
    hotel_id: str
    name: str
    city: str
    star_rating: int
    price_per_night: float
    currency: str
    amenities: List[str]
    summary: str


class PackageSearchRequest(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    market: Market = Market.UAE
    limit: int = Field(5, ge=1, le=20)


class PackageOffer(BaseModel):
    package_id: str
    title: str
    origin: str
    destination: str
    duration_days: int
    includes: List[str]
    price_from: float
    currency: str
    market: str
    highlights: List[str]


class ItineraryCreate(BaseModel):
    destination: str
    origin: Optional[str] = None
    days: int = Field(5, ge=1, le=21)
    travelers: int = Field(2, ge=1, le=20)
    budget: Optional[float] = None
    interests: List[str] = ["culture", "food", "sightseeing"]
    market: Market = Market.UAE


class ItineraryDay(BaseModel):
    day_number: int
    title: str
    activities: List[str]
    meals: str
    accommodation: str
    estimated_cost: Optional[float] = None


class ItineraryResponse(BaseModel):
    itinerary_id: str
    destination: str
    days: List[ItineraryDay]
    summary: str
    estimated_budget: Optional[float] = None
    currency: str


class PriceAlertCreate(BaseModel):
    phone: str
    email: Optional[str] = None
    origin: str
    destination: str
    departure_date: str
    target_price: float
    market: Market = Market.UAE


class PriceAlertResponse(BaseModel):
    alert_id: str
    phone: str
    email: Optional[str] = None
    origin: str
    destination: str
    departure_date: str
    target_price: float
    market: str
    status: str
    last_checked_price: Optional[float] = None
    created_at: str


class ReferralRegisterRequest(BaseModel):
    phone: str
    market: Market = Market.UAE


class ReferralApplyRequest(BaseModel):
    referral_code: str
    phone: str
