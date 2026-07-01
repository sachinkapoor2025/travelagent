"""Ad intelligence — DynamoDB."""

from fastapi import APIRouter

from app.schemas import AdAnalysisRequest, AdAnalysisResponse
from app.services.ad_intelligence import ad_intelligence
from app.storage.bookings_repo import booking_repo

router = APIRouter(prefix="/ads", tags=["ads"])


@router.post("/analyze", response_model=AdAnalysisResponse)
async def analyze_ads(payload: AdAnalysisRequest) -> AdAnalysisResponse:
    result = await ad_intelligence.analyze_route(
        payload.origin.upper(),
        payload.destination.upper(),
        payload.market,
        payload.platform,
    )

    await booking_repo.save_campaign(
        {
            "name": f"{payload.origin}-{payload.destination} {payload.platform}",
            "route_origin": payload.origin.upper(),
            "route_destination": payload.destination.upper(),
            "market": payload.market.value,
            "platform": payload.platform,
            "status": "analyzed",
            "competitor_analysis": {"insights": result.competitor_insights, "patterns": result.winning_patterns},
            "generated_ads": [v.model_dump() for v in result.ad_variants],
        }
    )
    return result


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
        }
        for c in campaigns
    ]
