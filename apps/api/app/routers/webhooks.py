"""Lead form webhooks from Meta and Google."""

from fastapi import APIRouter, Request

from app.services.webhooks import ingest_google_lead, ingest_meta_lead

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/meta-leads")
async def meta_leads_webhook(request: Request) -> dict:
    payload = await request.json()
    return await ingest_meta_lead(payload)


@router.get("/meta-leads")
async def meta_leads_verify(request: Request) -> str:
    params = request.query_params
    if params.get("hub.mode") == "subscribe":
        return params.get("hub.challenge", "")
    return "ok"


@router.post("/google-leads")
async def google_leads_webhook(request: Request) -> dict:
    payload = await request.json()
    return await ingest_google_lead(payload)
