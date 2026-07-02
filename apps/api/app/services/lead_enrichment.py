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
            "travel_intent": lead.get("travel_intent"),
            "notes": lead.get("notes"),
        }
        enriched["score"] = self._rule_score(enriched)
        enriched["temperature"] = temperature_from_score(enriched["score"])
        return enriched

    async def score_lead(self, lead: dict[str, Any]) -> int:
        if self.client:
            try:
                text = lead.get("notes") or lead.get("name") or ""
                has_phone = bool(lead.get("phone") and not lead.get("contact_synthetic"))
                prompt = f"""You are qualifying leads for TravelAI — a flight booking service for UAE, India, UK, Australia, US markets.

A REAL CUSTOMER LEAD is someone who needs to buy a flight ticket, asks for price/agent recommendation, mentions route/destination, or has urgency.

NOT a lead: travel agencies, deal channels, news, casual travel chat with no booking intent.

Source: {lead.get('source')}
Type: {lead.get('lead_segment', 'b2c')}
Market: {lead.get('market')}
Text: {text[:800]}
Has phone: {str(has_phone).lower()}

Score 1-10 (10 = route + date + price request now). Return JSON:
{{"score": int_1_to_10, "is_real_customer": bool, "action": "call_now|whatsapp_now|contact_via_post|email_nurture|discard", "reason": str}}

Map score to 0-100 as score * 10."""
                response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                data = json.loads(response.choices[0].message.content or "{}")
                if data.get("action") == "discard" or not data.get("is_real_customer", True):
                    return min(int(data.get("score", 2)) * 10, 30)
                return min(int(data.get("score", self._rule_score(lead) // 10)) * 10, 100)
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
        if lead.get("lead_segment") == "b2c":
            score += 12
        if lead.get("lead_segment") == "b2c" and lead.get("destination"):
            score += 8
        if lead.get("departure_date") and lead.get("lead_segment") == "b2c":
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
