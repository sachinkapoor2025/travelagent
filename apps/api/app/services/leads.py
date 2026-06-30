"""Lead scoring and pipeline management."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Lead, LeadSource, LeadStatus, Market

settings = get_settings()


def calculate_lead_score(lead: Lead) -> int:
    score = 0

    if lead.destination and lead.origin:
        score += 25
    if lead.departure_date:
        score += 20
        try:
            dep = datetime.strptime(lead.departure_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_until = (dep - datetime.now(timezone.utc)).days
            if 0 <= days_until <= 14:
                score += 25
            elif 15 <= days_until <= 45:
                score += 15
        except ValueError:
            pass
    if lead.passengers and lead.passengers > 1:
        score += 5
    if lead.budget_max and lead.budget_max >= 5000:
        score += 10
    if lead.cabin_class and lead.cabin_class.lower() in {"business", "first"}:
        score += 15
    if lead.source in {LeadSource.GOOGLE_ADS, LeadSource.WEBSITE, LeadSource.ABANDONED_SEARCH}:
        score += 10
    if lead.opt_in_voice:
        score += 5
    if lead.market == Market.UAE:
        score += 5

    return min(score, 100)


def classify_lead(score: int) -> str:
    if score >= settings.lead_hot_score_threshold:
        return "hot"
    if score >= settings.lead_warm_score_threshold:
        return "warm"
    return "cold"


async def create_or_update_lead(db: AsyncSession, data: dict) -> Lead:
    phone = data["phone"]
    result = await db.execute(select(Lead).where(Lead.phone == phone).order_by(Lead.created_at.desc()))
    lead = result.scalars().first()

    if lead:
        for key, value in data.items():
            if value is not None and hasattr(lead, key):
                setattr(lead, key, value)
    else:
        lead = Lead(**{k: v for k, v in data.items() if hasattr(Lead, k)})
        db.add(lead)

    lead.score = calculate_lead_score(lead)
    if lead.score >= settings.lead_hot_score_threshold:
        lead.status = LeadStatus.QUALIFIED
    await db.flush()
    return lead
