"""Ad intelligence — fetch, analyse, generate."""

import logging

from app.routers.auth import admin_required
from fastapi import APIRouter, HTTPException

from app.schemas import AdAnalysisRequest, AdAnalysisResponse, GeneratedAdPackage
from app.services.ad_intelligence import ad_intelligence
from app.storage.bookings_repo import booking_repo

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[admin_required()], prefix="/ads", tags=["ads"])


@router.post("/analyze", response_model=AdAnalysisResponse)
async def analyze_ads(payload: AdAnalysisRequest) -> AdAnalysisResponse:
    try:
        result = await ad_intelligence.analyze_route(
            payload.origin.upper(),
            payload.destination.upper(),
            payload.market,
            payload.platform,
        )
    except Exception as exc:
        logger.exception("Ad analyze failed")
        raise HTTPException(status_code=503, detail="Ad analysis failed — try again shortly") from exc

    try:
        await booking_repo.save_campaign(
            {
                "name": f"{payload.origin}-{payload.destination} {payload.platform}",
                "route_origin": payload.origin.upper(),
                "route_destination": payload.destination.upper(),
                "market": payload.market.value,
                "platform": payload.platform,
                "status": "analyzed",
                "competitor_analysis": {
                    "insights": result.competitor_insights,
                    "patterns": result.winning_patterns,
                    "gaps": result.gap_analysis,
                },
                "generated_ads": [v.model_dump() for v in result.ad_variants],
                "generated_package": result.generated_package.model_dump() if result.generated_package else None,
            }
        )
    except Exception:
        logger.exception("Failed to persist ad campaign — returning analysis anyway")

    return result


@router.get("/fetch")
async def fetch_competitor_ads(origin: str, destination: str, market: str = "uae") -> dict:
    from app.models import Market

    return await ad_intelligence.fetch_competitor_ads(origin.upper(), destination.upper(), Market(market))


@router.post("/generate", response_model=GeneratedAdPackage)
async def generate_superior_ad(payload: AdAnalysisRequest) -> GeneratedAdPackage:
    return await ad_intelligence.generate_superior_ad(
        payload.origin.upper(),
        payload.destination.upper(),
        payload.market,
    )


@router.get("/campaigns")
async def list_campaigns() -> list[dict]:
    campaigns = await booking_repo.list_campaigns()
    return [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "route": f"{c.get('route_origin')}-{c.get('route_destination')}",
            "market": c.get("market"),
            "platform": c.get("platform"),
            "status": c.get("status"),
            "top_ad": c.get("generated_ads", [None])[0] if c.get("generated_ads") else None,
            "generated_package": c.get("generated_package"),
        }
        for c in campaigns
    ]
