"""Background worker for lead callbacks and abandoned search recovery."""

import asyncio
import logging

from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_factory
from app.models import Lead, LeadStatus
from app.services.leads import classify_lead
from app.services.session import session_store
from app.services.voice import initiate_outbound_call

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel-ai-worker")
settings = get_settings()


async def process_hot_leads() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Lead)
            .where(Lead.status.in_([LeadStatus.NEW, LeadStatus.CONTACTED]))
            .where(Lead.score >= settings.lead_warm_score_threshold)
            .order_by(Lead.score.desc())
            .limit(10)
        )
        leads = result.scalars().all()

        for lead in leads:
            tier = classify_lead(lead.score)
            logger.info("Processing %s lead %s score=%s", tier, lead.id, lead.score)
            call_result = await initiate_outbound_call(
                lead.phone,
                {
                    "lead_id": str(lead.id),
                    "opt_in_voice": lead.opt_in_voice,
                    "on_dnc": False,
                    "origin": lead.origin,
                    "destination": lead.destination,
                    "departure_date": lead.departure_date,
                    "passengers": lead.passengers,
                    "market": lead.market.value,
                },
            )
            if call_result.get("success"):
                lead.status = LeadStatus.CONTACTED
        await db.commit()


async def run_worker() -> None:
    await session_store.connect()
    logger.info("TravelAI worker started")
    while True:
        try:
            await process_hot_leads()
        except Exception:
            logger.exception("Worker cycle failed")
        await asyncio.sleep(120)


if __name__ == "__main__":
    asyncio.run(run_worker())
