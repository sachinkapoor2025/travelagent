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
    chat,
    flights,
    health,
    hotels,
    itineraries,
    leads,
    payments,
    price_alerts,
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
    allow_credentials=True,
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
app.include_router(webhooks.router, prefix=API_PREFIX)
app.include_router(sms.router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "dashboard": "/dashboard",
        "markets": ["uae", "india"],
        "features": [
            "voice_agent",
            "whatsapp",
            "web_chat",
            "sms",
            "lead_engine",
            "meta_google_webhooks",
            "booking",
            "hotels",
            "packages",
            "itineraries",
            "price_alerts",
            "referrals",
            "payments",
            "ad_intelligence",
            "analytics",
            "email_nurture",
        ],
    }


@app.get("/dashboard")
async def dashboard():
    return FileResponse(Path(__file__).parent / "static" / "dashboard.html")
