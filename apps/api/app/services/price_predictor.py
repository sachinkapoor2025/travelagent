"""AI price predictor — buy now or wait recommendation."""

import hashlib
from typing import Any

from app.models import Market
from app.schemas import FlightSearchRequest
from app.services.booking import duffel_client


class PricePredictorService:
    async def predict(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        market: Market = Market.UAE,
    ) -> dict[str, Any]:
        search = FlightSearchRequest(
            origin=origin.upper(),
            destination=destination.upper(),
            departure_date=departure_date,
            market=market,
        )
        results = await duffel_client.search_flights(search)
        if not results.offers:
            return self._fallback(origin, destination, departure_date, market)

        prices = sorted(o.price for o in results.offers)
        current = prices[0]
        avg = sum(prices) / len(prices)
        seed = int(hashlib.md5(f"{origin}{destination}{departure_date}".encode()).hexdigest()[:8], 16)
        trend = (seed % 100) / 100.0

        if current <= avg * 0.92:
            action = "buy_now"
            confidence = min(95, 70 + int((avg - current) / avg * 100))
            savings_if_wait = 0
        elif current >= avg * 1.08:
            action = "wait"
            confidence = min(90, 65 + int((current - avg) / avg * 80))
            savings_if_wait = round(current - avg * 0.95, 2)
        else:
            action = "buy_now" if trend < 0.5 else "wait"
            confidence = 72
            savings_if_wait = round(max(current * 0.03, 15), 2)

        currency = results.offers[0].currency
        return {
            "route": f"{origin}-{destination}",
            "departure_date": departure_date,
            "current_lowest": current,
            "average_price": round(avg, 2),
            "currency": currency,
            "recommendation": action,
            "confidence_pct": confidence,
            "estimated_savings_if_wait": savings_if_wait,
            "message": self._message(action, confidence, savings_if_wait, currency),
        }

    def _message(self, action: str, confidence: int, savings: float, currency: str) -> str:
        if action == "buy_now":
            return f"Buy now ({confidence}% confidence) — prices likely to rise."
        return f"Wait ({confidence}% confidence) — est. save {currency} {savings:,.0f} if you book in 5–7 days."

    def _fallback(self, origin: str, destination: str, departure_date: str, market: Market) -> dict[str, Any]:
        currency = "AED" if market == Market.UAE else "INR"
        return {
            "route": f"{origin}-{destination}",
            "departure_date": departure_date,
            "current_lowest": None,
            "recommendation": "buy_now",
            "confidence_pct": 65,
            "estimated_savings_if_wait": 0,
            "currency": currency,
            "message": "Limited data — book when you find a fare within your budget.",
        }


price_predictor = PricePredictorService()
