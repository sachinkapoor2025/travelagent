"""Background jobs for scheduled Lambda worker."""

import logging

from app.config import get_settings
from app.services.voice import initiate_outbound_call
from app.storage.leads_repo import lead_repo

logger = logging.getLogger("travel-ai-worker")
settings = get_settings()


async def process_hot_leads() -> dict:
    leads = await lead_repo.get_hot_leads(limit=10)
    processed = 0

    for lead in leads:
        if lead.get("status") not in {"new", "contacted"}:
            continue
        logger.info("Processing lead %s score=%s", lead["id"], lead["score"])
        result = await initiate_outbound_call(
            lead["phone"],
            {
                "lead_id": lead["id"],
                "opt_in_voice": lead.get("opt_in_voice", False),
                "on_dnc": False,
                "origin": lead.get("origin"),
                "destination": lead.get("destination"),
                "departure_date": lead.get("departure_date"),
                "passengers": lead.get("passengers", 1),
                "market": lead.get("market", "uae"),
            },
        )
        if result.get("success"):
            await lead_repo.update_status(lead["id"], "contacted")
            processed += 1

    return {"processed": processed, "total_hot": len(leads)}
