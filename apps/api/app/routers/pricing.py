"""Dynamic pricing and AI price predictor endpoints."""

from fastapi import APIRouter

from app.models import Market
from app.services.dynamic_pricing import dynamic_pricing
from app.services.price_predictor import price_predictor

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/dynamic")
async def get_dynamic_pricing(
    origin: str,
    destination: str,
    departure_date: str,
    market: Market = Market.UAE,
) -> dict:
    return await dynamic_pricing.analyze_route(
        origin.upper(), destination.upper(), market, departure_date
    )


@router.get("/predict")
async def predict_price(
    origin: str,
    destination: str,
    departure_date: str,
    market: Market = Market.UAE,
) -> dict:
    return await price_predictor.predict(
        origin.upper(), destination.upper(), departure_date, market
    )
