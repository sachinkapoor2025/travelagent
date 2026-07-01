"""Fetch competitor ads from Meta Ad Library and Google Ads Transparency."""

from typing import Any

import httpx

from app.config import get_settings
from app.models import Market
from app.storage.dynamo import leads_store, now_iso

settings = get_settings()


class AdSourcesService:
    async def fetch_all(self, origin: str, destination: str, market: Market) -> dict[str, Any]:
        meta = await self.fetch_meta_ads(origin, destination, market)
        google = await self.fetch_google_ads(origin, destination, market)
        combined = meta + google
        await self._cache_ads(origin, destination, market, combined)
        return {"meta": meta, "google": google, "total": len(combined), "ads": combined}

    async def fetch_meta_ads(self, origin: str, destination: str, market: Market) -> list[dict[str, Any]]:
        query = f"flights {origin} {destination}"
        if settings.meta_access_token:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        "https://graph.facebook.com/v21.0/ads_archive",
                        params={
                            "access_token": settings.meta_access_token,
                            "ad_reached_countries": "AE" if market == Market.UAE else "IN",
                            "search_terms": query,
                            "ad_type": "ALL",
                            "fields": "id,ad_creative_bodies,ad_creative_link_titles,page_name,spend,impressions",
                            "limit": 25,
                        },
                    )
                    if response.status_code == 200:
                        data = response.json().get("data", [])
                        return [
                            {
                                "source": "meta",
                                "advertiser": item.get("page_name", "Unknown"),
                                "headline": (item.get("ad_creative_link_titles") or ["Travel deal"])[0],
                                "body": (item.get("ad_creative_bodies") or [""])[0],
                                "spend": item.get("spend"),
                                "impressions": item.get("impressions"),
                                "route": f"{origin}-{destination}",
                            }
                            for item in data
                        ]
            except Exception:
                pass
        return self._mock_meta_ads(origin, destination, market)

    async def fetch_google_ads(self, origin: str, destination: str, market: Market) -> list[dict[str, Any]]:
        if settings.serpapi_key:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params={
                        "engine": "google",
                        "q": f"flights {origin} to {destination}",
                        "api_key": settings.serpapi_key,
                        "gl": "ae" if market == Market.UAE else "in",
                        "hl": "en",
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    ads = data.get("ads", []) + data.get("shopping_results", [])
                    return [
                        {
                            "source": "google",
                            "advertiser": a.get("source", a.get("seller", "Google advertiser")),
                            "headline": a.get("title", ""),
                            "body": a.get("description", a.get("snippet", "")),
                            "link": a.get("link"),
                            "route": f"{origin}-{destination}",
                        }
                        for a in ads[:15]
                    ]
        return self._mock_google_ads(origin, destination, market)

    async def _cache_ads(self, origin: str, destination: str, market: Market, ads: list[dict[str, Any]]) -> None:
        store = leads_store()
        if not store.enabled:
            return
        key = f"ADS#{origin}#{destination}#{market.value}"
        store.put(
            key,
            "METADATA",
            {"origin": origin, "destination": destination, "market": market.value, "ads": ads, "fetched_at": now_iso()},
        )

    def _mock_meta_ads(self, origin: str, destination: str, market: Market) -> list[dict[str, Any]]:
        currency = "AED" if market == Market.UAE else "₹"
        brands = ["Emirates", "MakeMyTrip", "Cleartrip", "Musafir", "Akbar Travels"]
        return [
            {
                "source": "meta",
                "advertiser": brands[i % len(brands)],
                "headline": f"{origin}→{destination} from {currency}{899 + i * 100}",
                "body": "Book now. Free date change on select fares. AI assistant 24/7.",
                "route": f"{origin}-{destination}",
            }
            for i in range(5)
        ]

    def _mock_google_ads(self, origin: str, destination: str, market: Market) -> list[dict[str, Any]]:
        currency = "AED" if market == Market.UAE else "₹"
        return [
            {
                "source": "google",
                "advertiser": "eDreams",
                "headline": f"Cheap flights {origin} to {destination}",
                "body": f"Compare 500+ airlines from {currency}799. Instant confirmation.",
                "route": f"{origin}-{destination}",
            },
            {
                "source": "google",
                "advertiser": "Skyscanner",
                "headline": f"Direct flights {origin} {destination}",
                "body": "Find the best fare in seconds. No hidden fees.",
                "route": f"{origin}-{destination}",
            },
        ]


ad_sources = AdSourcesService()
