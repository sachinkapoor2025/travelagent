"""Import B2C leads from scrapers — unscored until LLM qualification runs."""

from __future__ import annotations

import logging
from typing import Any

from app.services.lead_enrichment import lead_enrichment
from app.services.lead_mining import lead_mining
from app.services.lead_segment import apply_segment, ensure_contact_phone
from app.services.miners.travel_parse import parse_travel_text

logger = logging.getLogger(__name__)


async def import_b2c_leads(
    raw_leads: list[dict[str, Any]],
    *,
    source_id: str,
    skip_deals: bool = True,
) -> dict[str, Any]:
    imported = 0
    skipped = 0
    errors = 0

    for raw in raw_leads:
        if skip_deals and raw.get("lead_category") == "deal_channel":
            skipped += 1
            continue
        if raw.get("call_ready") is False:
            skipped += 1
            continue

        lead = apply_segment(raw, default="b2c")
        lead.setdefault("lead_category", "consumer")
        lead.setdefault("scored", False)
        lead.setdefault("status", "new")
        lead.setdefault("source", source_id)

        text = lead.get("notes") or ""
        if text and not lead.get("destination"):
            parsed = parse_travel_text(text)
            for key in ("origin", "destination", "departure_date", "budget_max", "location"):
                if parsed.get(key) and not lead.get(key):
                    lead[key] = parsed[key]

        lead = ensure_contact_phone(lead)
        if not (lead.get("phone") or lead.get("notes") or lead.get("post_url")):
            skipped += 1
            continue

        try:
            enriched = await lead_enrichment.enrich_fast(lead)
            enriched["scored"] = False
            enriched.setdefault("score", 40)
            enriched.setdefault("temperature", "cold")
            await lead_mining._save_lead(enriched)  # noqa: SLF001
            imported += 1
        except Exception:
            logger.exception("Failed to import B2C lead from %s", source_id)
            errors += 1

    return {"imported": imported, "skipped": skipped, "errors": errors, "raw_found": len(raw_leads)}
