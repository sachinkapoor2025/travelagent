"""Background jobs for scheduled Lambda worker."""

import logging

from app.config import get_settings
from app.services.compliance import scrub_dnc
from app.services.voice import initiate_outbound_call
from app.storage.leads_repo import lead_repo

logger = logging.getLogger("travel-ai-worker")
settings = get_settings()


async def process_hot_leads() -> dict:
    leads = await lead_repo.get_hot_leads(limit=10)
    processed = 0

    for lead in leads:
        if lead.get("status") not in {"new", "contacted", "qualified"}:
            continue
        on_dnc = await scrub_dnc(lead["phone"])
        if on_dnc:
            continue
        logger.info("Processing lead %s score=%s temp=%s", lead["id"], lead["score"], lead.get("temperature"))
        result = await initiate_outbound_call(
            lead["phone"],
            {
                "lead_id": lead["id"],
                "opt_in_voice": lead.get("opt_in_voice", False),
                "on_dnc": on_dnc,
                "origin": lead.get("origin"),
                "destination": lead.get("destination"),
                "departure_date": lead.get("departure_date"),
                "passengers": lead.get("passengers", 1),
                "market": lead.get("market", "uae"),
                "preferred_language": lead.get("preferred_language", "en"),
                "temperature": lead.get("temperature", "hot"),
            },
        )
        if result.get("success"):
            await lead_repo.update_status(lead["id"], "contacted")
            processed += 1

    return {"processed": processed, "total_hot": len(leads)}
