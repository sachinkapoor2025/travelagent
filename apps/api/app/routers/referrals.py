"""Referral program endpoints."""

from fastapi import APIRouter, HTTPException

from app.schemas import ReferralApplyRequest, ReferralRegisterRequest
from app.services.referrals import referral_service

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.post("/register")
async def register_referrer(payload: ReferralRegisterRequest) -> dict:
    return await referral_service.register(payload.phone, payload.market.value)


@router.post("/apply")
async def apply_referral(payload: ReferralApplyRequest) -> dict:
    return await referral_service.apply(payload.referral_code, payload.phone)


@router.get("/stats/{phone}")
async def referral_stats(phone: str) -> dict:
    stats = await referral_service.stats(phone)
    if not stats:
        raise HTTPException(status_code=404, detail="Referrer not found")
    return stats
