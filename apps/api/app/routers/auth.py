"""Auth config — Cognito + optional portal API key."""

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.get("/config")
async def auth_config() -> dict:
    return {
        "cognito_region": settings.aws_region,
        "user_pool_id": settings.user_pool_id,
        "user_pool_client_id": settings.user_pool_client_id,
        "portal_auth_enabled": bool(settings.user_pool_id),
    }


async def optional_portal_auth(x_portal_key: str | None = Header(None, alias="X-Portal-Key")) -> bool:
    """When PORTAL_API_KEY is set, mutating routes require matching header."""
    if not settings.portal_api_key:
        return True
    if x_portal_key == settings.portal_api_key:
        return True
    raise HTTPException(status_code=401, detail="Invalid portal key")


def require_portal_auth():
    return Depends(optional_portal_auth)
