"""LLM lead qualification — buyer intent scoring for B2C scrapers."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.services.lead_enrichment import temperature_from_score
from app.storage.leads_repo import lead_repo

settings = get_settings()
logger = logging.getLogger(__name__)

QUALIFICATION_PROMPT = """You are qualifying leads for TravelAI — a flight booking service for UAE, India, UK, Australia, US markets.

A REAL CUSTOMER LEAD is someone who:
- Needs to buy a flight ticket
- Is asking for a price or agent recommendation
- Mentions a specific route or destination
- Has urgency (travel date, upcoming trip, urgent)

NOT a lead:
- Travel agencies or businesses
- Deal channels posting promotions
- News articles about travel
- People just discussing travel casually with no intent to book

Lead data:
Source: {source}
Type: {lead_type}
Market: {market}
Text: {text}
Has phone: {has_phone}

Score 1-10 where:
10 = Has specific route + date + asking for price RIGHT NOW
8-9 = Asking for agent/price, specific destination mentioned
6-7 = Clear travel intent, no specific date yet
4-5 = Travel adjacent business (B2B potential)
2-3 = Discussing travel, no booking intent
1 = Deal broadcast, spam, or irrelevant

Return ONLY this JSON:
{{
  "score": 8,
  "is_real_customer": true,
  "intent": "high",
  "language_to_use": "hindi",
  "action": "whatsapp_now",
  "estimated_route": "DXB-BOM",
  "call_opener": "Namaste! Dubai se Mumbai flight chahiye aapko?",
  "whatsapp_message": "Hi! Aapko Dubai se India flight chahiye? Aaj ka best rate AED 450 hai. Reply karo!",
  "reason": "Asked for Dubai to Mumbai flight price",
  "category": "b2c"
}}

Actions:
- call_now: score 9-10 AND has_phone=true
- whatsapp_now: score 7-10 AND has_phone=true
- contact_via_post: score 7-10 AND has_phone=false (reply to their Reddit/Telegram post)
- email_nurture: score 4-6
- discard: score 1-3
"""


async def score_unscored_leads(limit: int = 30) -> dict[str, Any]:
    """Run LLM qualification on leads with scored=false."""
    if not settings.openai_api_key:
        return {"scored": 0, "error": "OPENAI_API_KEY not configured"}

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    leads = await lead_repo.list_unscored_leads(limit=limit)
    scored_count = 0
    discarded = 0

    for lead in leads:
        try:
            result = await _qualify_lead(client, lead)
            if not result:
                continue

            llm_score = int(result.get("score", 3))
            is_customer = bool(result.get("is_real_customer", False))
            action = result.get("action", "discard")

            if action == "discard" or llm_score <= 3 or not is_customer:
                await lead_repo.update_lead_fields(lead["id"], {
                    "scored": True,
                    "lead_category": "discarded",
                    "score": llm_score * 10,
                    "status": "lost",
                    "scorer_action": action,
                    "scorer_reason": result.get("reason"),
                })
                discarded += 1
                continue

            score_100 = min(llm_score * 10, 100)
            updates: dict[str, Any] = {
                "scored": True,
                "score": score_100,
                "temperature": temperature_from_score(score_100),
                "scorer_action": action,
                "scorer_reason": result.get("reason"),
                "call_opener": result.get("call_opener"),
                "whatsapp_message": result.get("whatsapp_message"),
                "preferred_language": result.get("language_to_use") or lead.get("preferred_language"),
                "lead_category": result.get("category", "consumer"),
            }
            route = result.get("estimated_route")
            if route and "-" in route:
                parts = route.split("-", 1)
                updates["origin"] = parts[0]
                updates["destination"] = parts[1]

            if score_100 >= settings.lead_hot_score_threshold:
                updates["status"] = "qualified"

            await lead_repo.update_lead_fields(lead["id"], updates)
            scored_count += 1
        except Exception:
            logger.exception("Failed to score lead %s", lead.get("id"))

    return {"scored": scored_count, "discarded": discarded, "checked": len(leads)}


async def _qualify_lead(client: AsyncOpenAI, lead: dict[str, Any]) -> dict[str, Any] | None:
    text = lead.get("notes") or lead.get("name") or ""
    has_phone = bool(lead.get("phone") and not lead.get("contact_synthetic"))
    prompt = QUALIFICATION_PROMPT.format(
        source=lead.get("source", ""),
        lead_type=lead.get("lead_segment", "b2c"),
        market=lead.get("market", ""),
        text=text[:800],
        has_phone=str(has_phone).lower(),
    )
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)
