"""Dynamic pricing — competitor monitoring and price recommendations."""

from typing import Any

from app.models import Market
from app.schemas import FlightSearchRequest
from app.services.ad_sources import ad_sources
from app.services.booking import duffel_client
from app.storage.dynamo import leads_store, now_iso

settings = None


def _settings():
    global settings
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    return settings


class DynamicPricingService:
    async def analyze_route(self, origin: str, destination: str, market: Market, departure_date: str) -> dict[str, Any]:
        search = FlightSearchRequest(
            origin=origin.upper(),
            destination=destination.upper(),
            departure_date=departure_date,
            market=market,
        )
        duffel = await duffel_client.search_flights(search)
        our_best = min((o.price for o in duffel.offers), default=0)
        competitor_ads = await ad_sources.fetch_all(origin, destination, market)
        competitor_prices = self._extract_prices(competitor_ads.get("ads", []), market)

        competitor_best = min(competitor_prices) if competitor_prices else our_best * 1.05
        margin_pct = _settings().pricing_margin_pct
        recommended = round(our_best * (1 - margin_pct / 100), 2) if our_best else 0
        undercut = competitor_best - recommended if competitor_best else 0

        recommendation = "hold"
        if undercut > 0:
            recommendation = "undercut"
        elif our_best <= competitor_best:
            recommendation = "competitive"

        result = {
            "route": f"{origin}-{destination}",
            "departure_date": departure_date,
            "market": market.value,
            "our_best_price": our_best,
            "competitor_best_estimate": round(competitor_best, 2),
            "recommended_price": recommended,
            "undercut_amount": round(max(undercut, 0), 2),
            "recommendation": recommendation,
            "currency": "AED" if market == Market.UAE else "INR",
            "analyzed_at": now_iso(),
        }

        store = leads_store()
        if store.enabled:
            store.put(
                f"PRICING#{origin}#{destination}",
                "METADATA",
                result,
            )
        return result

    def _extract_prices(self, ads: list[dict[str, Any]], market: Market) -> list[float]:
        import re

        prices: list[float] = []
        for ad in ads:
            text = f"{ad.get('headline', '')} {ad.get('body', '')}"
            nums = re.findall(r"(?:AED|₹|INR|Rs\.?)\s*([\d,]+)", text, re.I)
            if not nums:
                nums = re.findall(r"from\s*([\d,]+)", text, re.I)
            for n in nums:
                try:
                    prices.append(float(n.replace(",", "")))
                except ValueError:
                    continue
        if not prices:
            base = 899 if market == Market.UAE else 29999
            prices = [base + i * 50 for i in range(3)]
        return prices


dynamic_pricing = DynamicPricingService()
