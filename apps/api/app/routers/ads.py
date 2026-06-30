"""Ad intelligence and campaign generation."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AdCampaign, Market
from app.schemas import AdAnalysisRequest, AdAnalysisResponse
from app.services.ad_intelligence import ad_intelligence

router = APIRouter(prefix="/ads", tags=["ads"])


@router.post("/analyze", response_model=AdAnalysisResponse)
async def analyze_ads(payload: AdAnalysisRequest, db: AsyncSession = Depends(get_db)) -> AdAnalysisResponse:
    result = await ad_intelligence.analyze_route(
        payload.origin.upper(),
        payload.destination.upper(),
        payload.market,
        payload.platform,
    )

    campaign = AdCampaign(
        name=f"{payload.origin}-{payload.destination} {payload.platform}",
        route_origin=payload.origin.upper(),
        route_destination=payload.destination.upper(),
        market=payload.market,
        platform=payload.platform,
        status="analyzed",
        competitor_analysis={"insights": result.competitor_insights, "patterns": result.winning_patterns},
        generated_ads=[v.model_dump() for v in result.ad_variants],
    )
    db.add(campaign)
    await db.flush()

    return result


@router.get("/campaigns")
async def list_campaigns(db: AsyncSession = Depends(get_db)) -> list[dict]:
    from sqlalchemy import select

    result = await db.execute(select(AdCampaign).order_by(AdCampaign.created_at.desc()).limit(20))
    campaigns = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "route": f"{c.route_origin}-{c.route_destination}",
            "market": c.market.value,
            "platform": c.platform,
            "status": c.status,
            "top_ad": c.generated_ads[0] if c.generated_ads else None,
        }
        for c in campaigns
    ]
