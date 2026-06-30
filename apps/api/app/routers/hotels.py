"""Hotel and package search endpoints."""

from fastapi import APIRouter

from app.schemas import HotelOffer, HotelSearchRequest, PackageOffer, PackageSearchRequest
from app.services.hotels import hotel_service

router = APIRouter(prefix="/hotels", tags=["hotels"])


@router.post("/search", response_model=list[HotelOffer])
async def search_hotels(payload: HotelSearchRequest) -> list[HotelOffer]:
    return await hotel_service.search_hotels(payload)


@router.post("/packages/search", response_model=list[PackageOffer])
async def search_packages(payload: PackageSearchRequest) -> list[PackageOffer]:
    return await hotel_service.search_packages(payload)
