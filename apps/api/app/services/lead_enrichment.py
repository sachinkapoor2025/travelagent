"""Lead enrichment and Hot/Warm/Cold scoring."""

import json
from typing import Any, Optional

from openai import AsyncOpenAI

from app.config import get_settings
from app.models import Market

settings = get_settings()


def temperature_from_score(score: int) -> str:
    if score >= settings.lead_hot_score_threshold:
        return "hot"
    if score >= settings.lead_warm_score_threshold:
        return "warm"
    return "cold"


class LeadEnrichmentService:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def enrich(self, lead: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(lead)
        enriched.setdefault("market", Market.UAE.value)
        enriched.setdefault("preferred_language", self._guess_language(lead))
        enriched.setdefault("travel_intent", self._guess_intent(lead))
        enriched["enrichment"] = {
            "employer": lead.get("employer") or lead.get("company"),
            "location": lead.get("location") or lead.get("city"),
            "source_detail": lead.get("source_detail") or lead.get("source"),
            "estimated_budget": lead.get("budget_max"),
        }
        enriched["score"] = await self.score_lead(enriched)
        enriched["temperature"] = temperature_from_score(enriched["score"])
        return enriched

    async def enrich_fast(self, lead: dict[str, Any]) -> dict[str, Any]:
        """Rule-based enrichment for bulk mining — avoids OpenAI per lead (Lambda timeout)."""
        enriched = dict(lead)
        enriched.setdefault("market", Market.UAE.value)
        enriched.setdefault("preferred_language", self._guess_language(lead))
        enriched.setdefault("travel_intent", self._guess_intent(lead))
        enriched["enrichment"] = {
            "employer": lead.get("employer") or lead.get("company"),
            "location": lead.get("location") or lead.get("city"),
            "source_detail": lead.get("source_detail") or lead.get("source"),
        }
        enriched["score"] = self._rule_score(enriched)
        enriched["temperature"] = temperature_from_score(enriched["score"])
        return enriched

    async def score_lead(self, lead: dict[str, Any]) -> int:
        if self.client:
            try:
                prompt = f"""Score this travel lead 0-100 for likelihood to book within 30 days.
Return JSON: {{"score": int, "reason": str, "temperature": "hot|warm|cold"}}

Lead: {json.dumps({k: lead.get(k) for k in ['phone','name','origin','destination','departure_date','market','source','employer','travel_intent'] if lead.get(k)})}"""
                response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                data = json.loads(response.choices[0].message.content or "{}")
                return int(data.get("score", self._rule_score(lead)))
            except Exception:
                pass
        return self._rule_score(lead)

    def _rule_score(self, lead: dict[str, Any]) -> int:
        score = 20
        if lead.get("origin") and lead.get("destination"):
            score += 25
        if lead.get("departure_date"):
            score += 20
        if lead.get("opt_in_voice"):
            score += 15
        if lead.get("budget_max"):
            score += 10
        if lead.get("source") in {"linkedin", "clay", "apollo", "referral"}:
            score += 15
        if lead.get("employer"):
            score += 5
        if lead.get("phone") and lead.get("source") in {"directories", "reddit", "telegram"}:
            score += 15
        if lead.get("location"):
            score += 5
        return min(score, 100)

    def _guess_language(self, lead: dict[str, Any]) -> str:
        market = lead.get("market", "uae")
        if lead.get("preferred_language"):
            return lead["preferred_language"]
        if market == "india":
            return "hi"
        if market == "uae":
            return "ar"
        return "en"

    def _guess_intent(self, lead: dict[str, Any]) -> str:
        if lead.get("destination") and lead.get("departure_date"):
            return "ready_to_book"
        if lead.get("destination"):
            return "researching"
        return "exploring"


lead_enrichment = LeadEnrichmentService()
