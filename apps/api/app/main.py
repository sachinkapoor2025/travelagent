"""TravelAI Agent — FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from fastapi.responses import FileResponse

from app.config import get_settings
from app.routers import (
    ads,
    analytics,
    auth,
    chat,
    flights,
    health,
    hotels,
    itineraries,
    lead_mining,
    leads,
    mcp,
    payments,
    price_alerts,
    pricing,
    referrals,
    sms,
    voice,
    webhooks,
    whatsapp,
)
from app.services.session import session_store

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await session_store.connect()
    yield
    await session_store.disconnect()


app = FastAPI(
    title=settings.app_name,
    description="AI travel agent for UAE and India — voice, WhatsApp, leads, booking, ads",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(leads.router, prefix=API_PREFIX)
app.include_router(flights.router, prefix=API_PREFIX)
app.include_router(voice.router, prefix=API_PREFIX)
app.include_router(whatsapp.router, prefix=API_PREFIX)
app.include_router(ads.router, prefix=API_PREFIX)
app.include_router(payments.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(hotels.router, prefix=API_PREFIX)
app.include_router(itineraries.router, prefix=API_PREFIX)
app.include_router(price_alerts.router, prefix=API_PREFIX)
app.include_router(referrals.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(webhooks.router, prefix=API_PREFIX)
app.include_router(sms.router, prefix=API_PREFIX)
app.include_router(lead_mining.router, prefix=API_PREFIX)
app.include_router(pricing.router, prefix=API_PREFIX)
app.include_router(mcp.router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "dashboard": "/dashboard",
        "markets": ["uae", "india"],
        "features": [
            "voice_agent",
            "multilingual_voice",
            "whatsapp",
            "whatsapp_booking",
            "web_chat",
            "agentic_booking",
            "sms",
            "lead_engine",
            "lead_mining",
            "outbound_ivr",
            "meta_google_webhooks",
            "booking",
            "hotels",
            "packages",
            "itineraries",
            "price_alerts",
            "price_predictor",
            "dynamic_pricing",
            "referrals",
            "payments",
            "ad_intelligence",
            "ai_ad_generator",
            "analytics",
            "email_nurture",
            "mcp_server",
            "self_healing_itinerary",
        ],
    }


@app.get("/dashboard")
async def dashboard():
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")
