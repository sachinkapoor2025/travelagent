"""Auto-action pipeline — hot leads get Vapi call, warm get WhatsApp."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.services.voice import initiate_outbound_call
from app.services.whatsapp import whatsapp_service
from app.storage.leads_repo import lead_repo

logger = logging.getLogger(__name__)
settings = get_settings()


async def auto_action_lead(lead: dict[str, Any]) -> str:
    """Return action taken: vapi_call, whatsapp, skipped, none."""
    score = int(lead.get("score", 0))
    phone = lead.get("phone")
    if not phone:
        return "none"

    on_dnc = await lead_repo.is_on_dnc(phone)
    if on_dnc:
        return "skipped_dnc"

    if score >= settings.lead_hot_score_threshold:
        result = await initiate_outbound_call(
            phone,
            {
                "lead_id": lead.get("id"),
                "opt_in_voice": True,
                "on_dnc": on_dnc,
                "origin": lead.get("origin"),
                "destination": lead.get("destination"),
                "departure_date": lead.get("departure_date"),
                "passengers": lead.get("passengers", 1),
                "market": lead.get("market", "uae"),
                "preferred_language": lead.get("preferred_language", "en"),
                "temperature": lead.get("temperature", "hot"),
                "source": lead.get("source"),
            },
        )
        if result.get("success"):
            await lead_repo.update_status(str(lead["id"]), "contacted")
            return "vapi_call" if not result.get("mock") else "vapi_mock"
        return "call_blocked"

    if score >= settings.lead_warm_score_threshold:
        dest = lead.get("destination") or "your destination"
        msg = (
            f"Hi {lead.get('name') or 'there'}! Sarah from TravelAI — I noticed you're planning travel to "
            f"{dest}. I can share live fares and packages. Reply here or call us anytime."
        )
        try:
            await whatsapp_service.send_text(phone, msg)
            await lead_repo.update_status(str(lead["id"]), "contacted")
            return "whatsapp"
        except Exception:
            logger.exception("WhatsApp auto-action failed for %s", phone)
            return "whatsapp_failed"

    return "queued"
