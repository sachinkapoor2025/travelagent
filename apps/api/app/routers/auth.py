"""Auth — Cognito login + portal API key."""

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.cognito_auth import require_admin

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


class LoginRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = Field(None, min_length=1)
    portal_key: Optional[str] = None


class LoginResponse(BaseModel):
    id_token: str
    access_token: Optional[str] = None
    expires_in: Optional[int] = None
    auth_type: str
    email: Optional[str] = None


@router.get("/config")
async def auth_config() -> dict:
    return {
        "cognito_region": settings.aws_region,
        "user_pool_id": settings.user_pool_id,
        "user_pool_client_id": settings.user_pool_client_id,
        "portal_auth_enabled": bool(settings.user_pool_id or settings.portal_api_key),
        "portal_key_auth": bool(settings.portal_api_key),
        "cognito_auth": bool(settings.user_pool_id),
    }


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    if settings.portal_api_key and payload.portal_key and payload.portal_key == settings.portal_api_key:
        return LoginResponse(id_token="portal-key", auth_type="api_key", email="admin@travelai.com")

    if not settings.user_pool_id or not settings.user_pool_client_id:
        raise HTTPException(status_code=503, detail="Admin login not configured — set Cognito or PORTAL_API_KEY")

    if not payload.email or not payload.password:
        raise HTTPException(status_code=400, detail="Email and password required")

    client = boto3.client("cognito-idp", region_name=settings.aws_region)
    try:
        resp = client.initiate_auth(
            ClientId=settings.user_pool_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": payload.email, "PASSWORD": payload.password},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"NotAuthorizedException", "UserNotFoundException"}:
            raise HTTPException(status_code=401, detail="Invalid email or password") from exc
        raise HTTPException(status_code=503, detail="Login service unavailable") from exc

    tokens = resp.get("AuthenticationResult", {})
    if not tokens.get("IdToken"):
        raise HTTPException(status_code=401, detail="Login failed")

    return LoginResponse(
        id_token=tokens["IdToken"],
        access_token=tokens.get("AccessToken"),
        expires_in=tokens.get("ExpiresIn"),
        auth_type="cognito",
        email=payload.email,
    )


@router.get("/me")
async def me(user: dict = Depends(require_admin)) -> dict:
    return {"email": user.get("email"), "auth_type": user.get("auth")}


def admin_required():
    return Depends(require_admin)
