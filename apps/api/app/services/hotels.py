"""Hotel search and travel package recommendations."""

from typing import Any, Optional

import httpx

from app.config import get_settings
from app.models import Market
from app.schemas import HotelOffer, HotelSearchRequest, PackageOffer, PackageSearchRequest

settings = get_settings()

# Curated UAE/India popular packages for demo + production seed
POPULAR_PACKAGES = [
    {
        "package_id": "pkg-dxb-maldives-5d",
        "title": "Dubai to Maldives — 5 Days All-Inclusive",
        "origin": "DXB",
        "destination": "MLE",
        "duration_days": 5,
        "includes": ["Return flights", "4-star resort", "Breakfast & dinner", "Airport transfers"],
        "price_from": 4299,
        "currency": "AED",
        "market": "uae",
        "highlights": ["Overwater villa upgrade available", "Snorkeling included"],
    },
    {
        "package_id": "pkg-bom-goa-4d",
        "title": "Mumbai to Goa — Beach Escape 4 Days",
        "origin": "BOM",
        "destination": "GOI",
        "duration_days": 4,
        "includes": ["Return flights", "3-star beach hotel", "Breakfast", "Scooter rental"],
        "price_from": 18999,
        "currency": "INR",
        "market": "india",
        "highlights": ["North Goa beaches", "Sunset cruise optional"],
    },
    {
        "package_id": "pkg-dxb-istanbul-6d",
        "title": "Dubai to Istanbul — Culture & Cuisine 6 Days",
        "origin": "DXB",
        "destination": "IST",
        "duration_days": 6,
        "includes": ["Return flights", "Boutique hotel", "City tour", "Bosphorus cruise"],
        "price_from": 5499,
        "currency": "AED",
        "market": "uae",
        "highlights": ["Hagia Sophia visit", "Turkish bath experience"],
    },
    {
        "package_id": "pkg-del-kashmir-7d",
        "title": "Delhi to Kashmir — Valley Paradise 7 Days",
        "origin": "DEL",
        "destination": "SXR",
        "duration_days": 7,
        "includes": ["Flights + train", "Houseboat stay", "Gulmarg day trip", "All meals"],
        "price_from": 45999,
        "currency": "INR",
        "market": "india",
        "highlights": ["Shikara ride on Dal Lake", "Snow activities in Gulmarg"],
    },
]


class HotelService:
    async def search_hotels(self, req: HotelSearchRequest) -> list[HotelOffer]:
        if settings.duffel_api_token:
            return await self._search_duffel_stays(req)
        return self._mock_hotels(req)

    async def search_packages(self, req: PackageSearchRequest) -> list[PackageOffer]:
        results = []
        for pkg in POPULAR_PACKAGES:
            if req.market.value != pkg["market"]:
                continue
            if req.origin and req.origin.upper() != pkg["origin"]:
                continue
            if req.destination and req.destination.upper() != pkg["destination"]:
                continue
            results.append(PackageOffer(**pkg))
        if not results and req.market == Market.UAE:
            results = [PackageOffer(**p) for p in POPULAR_PACKAGES if p["market"] == "uae"][:3]
        elif not results:
            results = [PackageOffer(**p) for p in POPULAR_PACKAGES if p["market"] == "india"][:3]
        return results[: req.limit]

    async def _search_duffel_stays(self, req: HotelSearchRequest) -> list[HotelOffer]:
        headers = {"Authorization": f"Bearer {settings.duffel_api_token}", "Duffel-Version": "v2"}
        params = {
            "location[latitude]": "25.2532" if req.city.upper() in {"DXB", "DUBAI"} else "19.0760",
            "location[longitude]": "55.3657" if req.city.upper() in {"DXB", "DUBAI"} else "72.8777",
            "check_in_date": req.check_in,
            "check_out_date": req.check_out,
            "rooms": req.rooms,
            "guests": [{"type": "adult"} for _ in range(req.guests)],
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.duffel.com/stays/search",
                    headers=headers,
                    params=params,
                )
                if response.status_code != 200:
                    return self._mock_hotels(req)
                data = response.json()
                offers = []
                for item in data.get("data", [])[:5]:
                    offers.append(
                        HotelOffer(
                            hotel_id=item.get("id", ""),
                            name=item.get("name", "Hotel"),
                            city=req.city,
                            star_rating=item.get("rating", 4),
                            price_per_night=float(item.get("cheapest_rate_total_amount", 500)),
                            currency=item.get("cheapest_rate_currency", "AED"),
                            amenities=["WiFi", "Pool", "Breakfast"],
                            summary=f"{item.get('name', 'Hotel')} in {req.city}",
                        )
                    )
                return offers or self._mock_hotels(req)
        except Exception:
            return self._mock_hotels(req)

    def _mock_hotels(self, req: HotelSearchRequest) -> list[HotelOffer]:
        currency = "AED" if req.market == Market.UAE else "INR"
        base = 450 if currency == "AED" else 3500
        names = ["Marina View Hotel", "Grand Palace Resort", "City Center Suites", "Beachfront Inn"]
        return [
            HotelOffer(
                hotel_id=f"hotel-{i}",
                name=names[i % len(names)],
                city=req.city,
                star_rating=4 + (i % 2),
                price_per_night=base * (1 + i * 0.3),
                currency=currency,
                amenities=["WiFi", "Pool", "Gym", "Breakfast"],
                summary=f"{names[i % len(names)]} — {req.nights} nights from {currency} {base}",
            )
            for i in range(min(4, req.limit))
        ]


hotel_service = HotelService()
