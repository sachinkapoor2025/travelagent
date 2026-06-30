"""Itinerary builder endpoints."""

from fastapi import APIRouter, HTTPException

from app.schemas import ItineraryCreate, ItineraryResponse
from app.services.itinerary import itinerary_service

router = APIRouter(prefix="/itineraries", tags=["itineraries"])


@router.post("", response_model=ItineraryResponse, status_code=201)
async def create_itinerary(payload: ItineraryCreate) -> ItineraryResponse:
    return await itinerary_service.create(payload)


@router.get("/{itinerary_id}", response_model=ItineraryResponse)
async def get_itinerary(itinerary_id: str) -> ItineraryResponse:
    result = await itinerary_service.get(itinerary_id)
    if not result:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    return result
