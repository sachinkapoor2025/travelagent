"""Lead mining, Clay webhooks, outbound campaigns."""

from typing import Any

from app.routers.auth import admin_required
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings
from app.services.lead_mining import lead_mining
from app.services.worker_jobs import process_hot_leads

router = APIRouter(dependencies=[admin_required()], prefix="/lead-mining", tags=["lead-mining"])
settings = get_settings()


@router.post("/webhook/clay")
async def clay_webhook(request: Request, x_clay_secret: str | None = Header(default=None)) -> dict[str, Any]:
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
    mined = await lead_mining.process_mined_leads()
    hot = await process_hot_leads()
    return {"mined_campaign": mined, "hot_leads": hot}
