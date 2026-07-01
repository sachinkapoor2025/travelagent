"""Lead scoring and pipeline classification — DynamoDB-only."""

from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.models import LeadSource, Market

settings = get_settings()


def calculate_lead_score(lead: Any) -> int:
    score = 0

    origin = getattr(lead, "origin", None) or (lead.get("origin") if isinstance(lead, dict) else None)
    destination = getattr(lead, "destination", None) or (lead.get("destination") if isinstance(lead, dict) else None)
    departure_date = getattr(lead, "departure_date", None) or (lead.get("departure_date") if isinstance(lead, dict) else None)
    passengers = getattr(lead, "passengers", 1) or (lead.get("passengers", 1) if isinstance(lead, dict) else 1)
    budget_max = getattr(lead, "budget_max", None) or (lead.get("budget_max") if isinstance(lead, dict) else None)
    cabin_class = getattr(lead, "cabin_class", None) or (lead.get("cabin_class") if isinstance(lead, dict) else None)
    source = getattr(lead, "source", None) or (lead.get("source") if isinstance(lead, dict) else None)
    opt_in_voice = getattr(lead, "opt_in_voice", False) or (lead.get("opt_in_voice", False) if isinstance(lead, dict) else False)
    market = getattr(lead, "market", None) or (lead.get("market") if isinstance(lead, dict) else None)

    if destination and origin:
        score += 25
    if departure_date:
        score += 20
        try:
            dep = datetime.strptime(str(departure_date), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_until = (dep - datetime.now(timezone.utc)).days
            if 0 <= days_until <= 14:
                score += 25
            elif 15 <= days_until <= 45:
                score += 15
        except ValueError:
            pass
    if passengers and int(passengers) > 1:
        score += 5
    if budget_max and float(budget_max) >= 5000:
        score += 10
    if cabin_class and str(cabin_class).lower() in {"business", "first"}:
        score += 15

    high_intent_sources = {LeadSource.GOOGLE_ADS, LeadSource.WEBSITE, LeadSource.ABANDONED_SEARCH}
    if isinstance(source, LeadSource) and source in high_intent_sources:
        score += 10
    elif isinstance(source, str) and source in {s.value for s in high_intent_sources}:
        score += 10

    if opt_in_voice:
        score += 5

    if market == Market.UAE or market == Market.UAE.value or market == "uae":
        score += 5

    return min(score, 100)


def classify_lead(score: int) -> str:
    if score >= settings.lead_hot_score_threshold:
        return "hot"
    if score >= settings.lead_warm_score_threshold:
        return "warm"
    return "cold"
