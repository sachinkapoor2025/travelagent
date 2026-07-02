"""Lead mining, Clay webhooks, outbound campaigns, automated sources."""

import logging
from typing import Any, Optional

from app.routers.auth import admin_required
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings
from app.services.lead_mining import lead_mining
from app.services.mining_config import get_sources
from app.services.mining_progress import DEFAULT_BATCH_SIZE, get_progress, reset_progress
from app.services.miners.orchestrator import MINERS, run_all_enabled, run_source_batch

KNOWN_SOURCES = set(MINERS) | {"directories", "clay", "apollo", "telegram", "reddit_rss", "twitter"}
from app.services.worker_jobs import process_hot_leads

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[admin_required()], prefix="/lead-mining", tags=["lead-mining"])
settings = get_settings()


@router.get("/dashboard")
async def mining_dashboard() -> dict[str, Any]:
    data = await lead_mining.dashboard()
    progress = {}
    for source_id in ("reddit_rss", "telegram", "twitter", "b2c", "b2b", "directories"):
        progress[source_id] = get_progress(source_id)
    data["progress"] = progress
    return data


@router.get("/progress/{source_id}")
async def mining_progress(source_id: str) -> dict[str, Any]:
    if source_id not in KNOWN_SOURCES:
        raise HTTPException(status_code=404, detail="Unknown source")
    return get_progress(source_id)


@router.get("/sources")
async def list_sources() -> dict[str, Any]:
    return {"sources": get_sources()}


@router.post("/sources/{source_id}/toggle")
async def toggle_source(source_id: str, enabled: bool = True) -> dict[str, Any]:
    from app.services.mining_config import set_source_enabled

    try:
        sources = set_source_enabled(source_id, enabled)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown source") from exc
    return {"source_id": source_id, "enabled": enabled, "sources": sources}


@router.post("/run/{source_id}")
async def run_miner(
    source_id: str,
    force: bool = True,
    sync: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    cursor: Optional[int] = None,
    reset: bool = False,
) -> dict[str, Any]:
    """Queue or run a batched miner (100–200 leads per batch, worldwide)."""
    if source_id not in KNOWN_SOURCES:
        raise HTTPException(status_code=404, detail="Unknown source")
    if source_id in {"clay", "apollo"}:
        raise HTTPException(status_code=400, detail="Use webhook import for Clay/Apollo")

    batch_size = max(50, min(batch_size, 200))

    if not sync:
        from app.services.miner_invoke import invoke_miner_async

        result = invoke_miner_async(
            source_id,
            batch_size=batch_size,
            cursor=cursor,
            reset=reset,
        )
        if result.get("queued"):
            return result
        logger.warning("Async invoke failed, falling back to sync: %s", result.get("error"))

    try:
        return await run_source_batch(
            source_id,
            force=force,
            batch_size=batch_size,
            cursor=cursor,
            reset=reset,
        )
    except Exception as exc:
        logger.exception("Miner run failed for %s", source_id)
        raise HTTPException(status_code=503, detail=f"Lead fetch failed: {exc}") from exc


@router.post("/reset/{source_id}")
async def reset_miner_progress(source_id: str) -> dict[str, Any]:
    if source_id not in KNOWN_SOURCES:
        raise HTTPException(status_code=404, detail="Unknown source")
    segment = "b2b" if source_id in {"b2b", "directories"} else "b2c"
    return reset_progress(source_id, segment=segment)


@router.post("/run-all")
async def run_all_miners() -> dict[str, Any]:
    return await run_all_enabled()


@router.post("/webhook/clay")
async def clay_webhook(request: Request, x_clay_secret: Optional[str] = Header(default=None)) -> dict[str, Any]:
    if settings.clay_webhook_secret and x_clay_secret != settings.clay_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    payload = await request.json()
    return await lead_mining.ingest_webhook(payload, source="clay")


@router.post("/webhook/apollo")
async def apollo_webhook(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return await lead_mining.ingest_webhook(payload, source="apollo")


@router.post("/import")
async def import_leads(leads: list[dict[str, Any]]) -> dict[str, Any]:
    return await lead_mining.import_batch(leads, source="manual")


@router.post("/campaign/run")
async def run_outbound_campaign() -> dict[str, Any]:
    mined = await run_all_enabled()
    hot = await process_hot_leads()
    return {"miners": mined, "hot_leads": hot}
