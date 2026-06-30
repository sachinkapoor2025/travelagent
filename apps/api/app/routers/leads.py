"""Lead management and outbound call triggering."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import DncEntry, Lead, LeadSource, LeadStatus
from app.schemas import LeadCreate, LeadResponse
from app.services.compliance import can_outbound_call, detect_market_from_phone
from app.services.leads import create_or_update_lead
from app.services.voice import initiate_outbound_call

router = APIRouter(prefix="/leads", tags=["leads"])
settings = get_settings()


@router.post("", response_model=LeadResponse, status_code=201)
async def create_lead(
    payload: LeadCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Lead:
    data = payload.model_dump()
    if data.get("metadata"):
        data["metadata_json"] = data.pop("metadata")
    if not data.get("market"):
        data["market"] = detect_market_from_phone(payload.phone)

    lead = await create_or_update_lead(db, data)

    if payload.opt_in_voice or payload.phone in settings.twilio_whitelist:
        background_tasks.add_task(_trigger_callback, lead)

    return lead


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    status: Optional[LeadStatus] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[Lead]:
    query = select(Lead).order_by(Lead.score.desc(), Lead.created_at.desc()).limit(limit)
    if status:
        query = query.where(Lead.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: UUID, db: AsyncSession = Depends(get_db)) -> Lead:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("/{lead_id}/call")
async def trigger_call(lead_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    dnc = await db.execute(select(DncEntry).where(DncEntry.phone == lead.phone))
    on_dnc = dnc.scalars().first() is not None

    result = await initiate_outbound_call(
        lead.phone,
        {
            "lead_id": str(lead.id),
            "opt_in_voice": lead.opt_in_voice,
            "on_dnc": on_dnc,
            "origin": lead.origin,
            "destination": lead.destination,
            "departure_date": lead.departure_date,
            "passengers": lead.passengers,
            "market": lead.market.value,
        },
    )
    if not result.get("success"):
        raise HTTPException(status_code=403, detail=result.get("reason"))
    return result


@router.post("/{lead_id}/dnc")
async def add_to_dnc(lead_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    existing = await db.execute(select(DncEntry).where(DncEntry.phone == lead.phone))
    if not existing.scalars().first():
        db.add(DncEntry(phone=lead.phone, market=lead.market, reason="Customer request"))
    lead.status = LeadStatus.DNC
    return {"status": "added_to_dnc", "phone": lead.phone}


async def _trigger_callback(lead: Lead) -> None:
    import asyncio

    await asyncio.sleep(settings.lead_callback_delay_seconds)
    await initiate_outbound_call(
        lead.phone,
        {
            "lead_id": str(lead.id),
            "opt_in_voice": lead.opt_in_voice,
            "on_dnc": False,
            "origin": lead.origin,
            "destination": lead.destination,
            "departure_date": lead.departure_date,
            "passengers": lead.passengers,
            "market": lead.market.value,
            "source": LeadSource.WEBSITE.value,
        },
    )
