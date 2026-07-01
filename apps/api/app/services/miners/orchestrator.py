"""Orchestrate all lead mining sources."""

from __future__ import annotations

import logging
from typing import Any

from app.services.lead_enrichment import lead_enrichment
from app.services.lead_mining import lead_mining
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

MAX_IMPORT_PER_RUN = 30


async def run_source(source_id: str, force: bool = False, fast: bool = True) -> dict[str, Any]:
    sources = get_sources()
    if source_id in {"clay", "apollo"}:
        return {
            "source": source_id,
            "skipped": True,
            "reason": "Webhook-only source — configure Clay/Apollo to POST to /lead-mining/webhook/" + source_id,
        }
    if source_id not in MINERS and source_id != "directories":
        return {"error": f"Unknown source {source_id}"}
    if not force and not sources.get(source_id, {}).get("enabled", False):
        return {"skipped": True, "reason": "disabled"}

    try:
        if source_id == "directories":
            raw_leads = await mine_directories(fast=fast)
        else:
            raw_leads = await MINERS[source_id]()
    except Exception as exc:
        logger.exception("Miner fetch failed for %s", source_id)
        return {"source": source_id, "error": str(exc), "imported": 0, "raw_found": 0}

    imported = 0
    errors = 0

    for raw in raw_leads[:MAX_IMPORT_PER_RUN]:
        if not raw.get("phone") and not raw.get("destination"):
            continue
        try:
            enriched = await lead_enrichment.enrich_fast(raw)
            await lead_mining._save_lead(enriched)  # noqa: SLF001 — internal reuse
            imported += 1
        except Exception:
            logger.exception("Failed to import mined lead from %s", source_id)
            errors += 1

    stats = {
        "imported": imported,
        "raw_found": len(raw_leads),
        "errors": errors,
        "actions": {"queued": imported},
    }
    try:
        record_run(source_id, stats)
    except Exception:
        logger.exception("Failed to record mining run for %s", source_id)

    return {"source": source_id, **stats}


async def run_all_enabled() -> dict[str, Any]:
    results = {}
    for source_id in MINERS:
        try:
            results[source_id] = await run_source(source_id, fast=False)
        except Exception as exc:
            logger.exception("Miner %s failed", source_id)
            results[source_id] = {"error": str(exc)}
    return results
