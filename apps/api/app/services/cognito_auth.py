"""Verify Cognito JWT tokens for admin portal access."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Optional
from urllib.request import urlopen

from fastapi import Header, HTTPException
from jose import JWTError, jwk, jwt

from app.config import get_settings

settings = get_settings()


@lru_cache
def _jwks_url() -> str:
    region = settings.aws_region
    pool = settings.user_pool_id
    return f"https://cognito-idp.{region}.amazonaws.com/{pool}/.well-known/jwks.json"


@lru_cache
def _load_jwks() -> dict[str, Any]:
    with urlopen(_jwks_url(), timeout=5) as resp:  # nosec B310 — trusted AWS JWKS URL
        return json.loads(resp.read())


def verify_cognito_token(token: str) -> dict[str, Any]:
    if not settings.user_pool_id:
        raise HTTPException(status_code=503, detail="Cognito not configured")
    try:
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        jwks = _load_jwks()
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if not key:
            raise HTTPException(status_code=401, detail="Invalid token key")
        rsa_key = jwk.construct(key)
        return jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=settings.user_pool_client_id,
            issuer=f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.user_pool_id}",
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc


async def require_admin(
    authorization: Optional[str] = Header(None),
    x_portal_key: Optional[str] = Header(None, alias="X-Portal-Key"),
) -> dict[str, Any]:
    """Accept Cognito Bearer token or shared portal API key."""
    if settings.portal_api_key and x_portal_key == settings.portal_api_key:
        return {"sub": "portal-key", "email": "portal@travelai.com", "auth": "api_key"}

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token == "portal-key" and settings.portal_api_key:
            return {"sub": "portal-key", "email": "portal@travelai.com", "auth": "api_key"}
        claims = verify_cognito_token(token)
        return {**claims, "auth": "cognito"}

    raise HTTPException(status_code=401, detail="Login required")
