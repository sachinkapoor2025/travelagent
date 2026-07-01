"""Lead management — DynamoDB."""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from typing import Optional

from app.models import LeadStatus
from app.routers.auth import admin_required
from app.schemas import LeadCreate, LeadResponse
from app.services.compliance import detect_market_from_phone
from app.services.voice import initiate_outbound_call
from app.storage.leads_repo import lead_repo

router = APIRouter(prefix="/leads", tags=["leads"], dependencies=[admin_required()])


@router.post("", response_model=LeadResponse, status_code=201)
async def create_lead(payload: LeadCreate) -> LeadResponse:
    data = payload.model_dump()
    if data.get("metadata"):
        data["metadata_json"] = data.pop("metadata")
    if not data.get("market"):
        data["market"] = detect_market_from_phone(payload.phone).value

    lead = await lead_repo.create_or_update(data)
    return LeadResponse(**lead)


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    status: Optional[LeadStatus] = None,
    market: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
) -> list[LeadResponse]:
    leads = await lead_repo.list_leads(
        status=status.value if status else None,
        market=market,
        source=source,
        q=q,
        limit=limit,
    )
    return [LeadResponse(**l) for l in leads]


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: UUID) -> LeadResponse:
    lead = await lead_repo.get_by_id(str(lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadResponse(**lead)


@router.post("/{lead_id}/call")
async def trigger_call(lead_id: UUID) -> dict:
    lead = await lead_repo.get_by_id(str(lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    on_dnc = await lead_repo.is_on_dnc(lead["phone"])
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
        },
    )
    if not result.get("success"):
        raise HTTPException(status_code=403, detail=result.get("reason"))
    return result


@router.post("/{lead_id}/dnc")
async def add_to_dnc(lead_id: UUID) -> dict:
    lead = await lead_repo.get_by_id(str(lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    await lead_repo.add_to_dnc(lead["phone"], lead.get("market", "uae"))
    await lead_repo.update_status(str(lead_id), LeadStatus.DNC.value)
    return {"status": "added_to_dnc", "phone": lead["phone"]}

