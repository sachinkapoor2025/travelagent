"""Orchestrate all lead mining sources."""

from __future__ import annotations

import logging
from typing import Any

from app.services.lead_enrichment import lead_enrichment
from app.services.lead_mining import lead_mining
from app.services.miners.auto_action import auto_action_lead
from app.services.miners.directories import mine_directories
from app.services.miners.reddit import mine_reddit
from app.services.miners.telegram import mine_telegram
from app.services.mining_config import get_sources, record_run

logger = logging.getLogger(__name__)

MINERS = {
    "reddit": mine_reddit,
    "telegram": mine_telegram,
    "directories": mine_directories,
}


async def run_source(source_id: str) -> dict[str, Any]:
    sources = get_sources()
    if source_id not in MINERS:
        return {"error": f"Unknown source {source_id}"}
    if not sources.get(source_id, {}).get("enabled", False):
        return {"skipped": True, "reason": "disabled"}

    raw_leads = await MINERS[source_id]()
    imported = 0
    actions: dict[str, int] = {}

    for raw in raw_leads:
        if not raw.get("phone") and not raw.get("destination"):
            continue
        enriched = await lead_enrichment.enrich(raw)
        saved = await lead_mining._save_lead(enriched)  # noqa: SLF001 — internal reuse
        imported += 1
        action = await auto_action_lead(saved)
        actions[action] = actions.get(action, 0) + 1

    stats = {"imported": imported, "raw_found": len(raw_leads), "actions": actions}
    record_run(source_id, stats)
    return {"source": source_id, **stats}


async def run_all_enabled() -> dict[str, Any]:
    results = {}
    for source_id in MINERS:
        try:
            results[source_id] = await run_source(source_id)
        except Exception as exc:
            logger.exception("Miner %s failed", source_id)
            results[source_id] = {"error": str(exc)}
    return results
