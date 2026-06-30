"""AI-powered day-by-day itinerary builder."""

from typing import Any, Optional
from uuid import uuid4

from openai import AsyncOpenAI

from app.config import get_settings
from app.schemas import ItineraryCreate, ItineraryDay, ItineraryResponse
from app.storage.dynamo import DynamoStore, now_iso

settings = get_settings()


class ItineraryService:
    def __init__(self) -> None:
        self.store = DynamoStore(settings.itineraries_table)
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def create(self, req: ItineraryCreate) -> ItineraryResponse:
        days = await self._generate_days(req)
        itinerary_id = str(uuid4())
        record = {
            "itinerary_id": itinerary_id,
            "destination": req.destination,
            "origin": req.origin,
            "days_count": req.days,
            "travelers": req.travelers,
            "budget": req.budget,
            "interests": req.interests,
            "market": req.market.value,
            "days": [d.model_dump() for d in days],
            "created_at": now_iso(),
        }

        if self.store.enabled:
            self.store.put(f"ITINERARY#{itinerary_id}", "METADATA", record)

        return ItineraryResponse(
            itinerary_id=itinerary_id,
            destination=req.destination,
            days=days,
            summary=f"{req.days}-day {req.destination} itinerary for {req.travelers} travelers",
            estimated_budget=req.budget,
            currency="AED" if req.market.value == "uae" else "INR",
        )

    async def get(self, itinerary_id: str) -> Optional[ItineraryResponse]:
        if not self.store.enabled:
            return None
        item = self.store.get(f"ITINERARY#{itinerary_id}", "METADATA")
        if not item:
            return None
        return ItineraryResponse(
            itinerary_id=item["itinerary_id"],
            destination=item["destination"],
            days=[ItineraryDay(**d) for d in item.get("days", [])],
            summary=f"{item['days_count']}-day {item['destination']} itinerary",
            estimated_budget=item.get("budget"),
            currency="AED" if item.get("market") == "uae" else "INR",
        )

    async def _generate_days(self, req: ItineraryCreate) -> list[ItineraryDay]:
        if self.client:
            return await self._ai_generate(req)
        return self._template_days(req)

    async def _ai_generate(self, req: ItineraryCreate) -> list[ItineraryDay]:
        prompt = (
            f"Create a {req.days}-day travel itinerary for {req.destination}. "
            f"Travelers: {req.travelers}. Budget: {req.budget}. Interests: {', '.join(req.interests)}. "
            f"Market: {req.market.value}. Return JSON array of days with day_number, title, "
            f"activities (list), meals, accommodation, estimated_cost."
        )
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a travel itinerary expert. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        import json

        try:
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            raw_days = parsed.get("days", parsed.get("itinerary", []))
            return [ItineraryDay(**d) for d in raw_days[: req.days]]
        except Exception:
            return self._template_days(req)

    def _template_days(self, req: ItineraryCreate) -> list[ItineraryDay]:
        templates = {
            "DXB": ["Burj Khalifa & Dubai Mall", "Desert Safari", "Old Dubai & Gold Souk", "Beach & Marina"],
            "MLE": ["Resort check-in & snorkeling", "Island hopping", "Sunset cruise", "Spa day"],
            "GOI": ["Calangute Beach", "Fort Aguada", "Anjuna flea market", "Dudhsagar Falls trip"],
            "IST": ["Sultanahmet & Hagia Sophia", "Grand Bazaar", "Bosphorus cruise", "Asian side tour"],
            "BOM": ["Gateway of India", "Elephanta Caves", "Colaba cafes", "Bollywood studio tour"],
        }
        activities_pool = templates.get(req.destination.upper(), ["City tour", "Local cuisine", "Shopping", "Relax"])
        days = []
        for i in range(req.days):
            days.append(
                ItineraryDay(
                    day_number=i + 1,
                    title=f"Day {i + 1}: {activities_pool[i % len(activities_pool)]}",
                    activities=[activities_pool[i % len(activities_pool)], "Free time", "Local dinner"],
                    meals="Breakfast included",
                    accommodation="Hotel" if i < req.days - 1 else "Departure",
                    estimated_cost=req.budget / req.days if req.budget else None,
                )
            )
        return days


itinerary_service = ItineraryService()
