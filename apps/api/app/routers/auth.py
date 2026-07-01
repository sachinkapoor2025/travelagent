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


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    name: Optional[str] = None


class ConfirmRequest(BaseModel):
    email: str
    code: str = Field(..., min_length=4)


class ResendRequest(BaseModel):
    email: str


def _cognito_client():
    return boto3.client("cognito-idp", region_name=settings.aws_region)


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

    client = _cognito_client()
    try:
        resp = client.initiate_auth(
            ClientId=settings.user_pool_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": payload.email, "PASSWORD": payload.password},
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UserNotConfirmedException":
            raise HTTPException(
                status_code=403,
                detail="Email not confirmed — check your inbox or use Confirm Email",
            ) from exc
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


@router.post("/register")
async def register(payload: RegisterRequest) -> dict:
    if not settings.user_pool_id or not settings.user_pool_client_id:
        raise HTTPException(status_code=503, detail="Registration not configured")

    attrs = [{"Name": "email", "Value": payload.email}]
    if payload.name:
        attrs.append({"Name": "name", "Value": payload.name})

    client = _cognito_client()
    try:
        client.sign_up(
            ClientId=settings.user_pool_client_id,
            Username=payload.email,
            Password=payload.password,
            UserAttributes=attrs,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UsernameExistsException":
            raise HTTPException(status_code=409, detail="An account with this email already exists") from exc
        if code == "InvalidPasswordException":
            raise HTTPException(status_code=400, detail="Password must be 8+ chars with upper, lower, and number") from exc
        raise HTTPException(status_code=503, detail="Registration unavailable") from exc

    return {
        "message": "Account created — check your email for a confirmation code",
        "email": payload.email,
        "next_step": "confirm",
    }


@router.post("/confirm")
async def confirm(payload: ConfirmRequest) -> dict:
    if not settings.user_pool_id or not settings.user_pool_client_id:
        raise HTTPException(status_code=503, detail="Registration not configured")

    client = _cognito_client()
    try:
        client.confirm_sign_up(
            ClientId=settings.user_pool_client_id,
            Username=payload.email,
            ConfirmationCode=payload.code,
        )
        client.admin_add_user_to_group(
            UserPoolId=settings.user_pool_id,
            Username=payload.email,
            GroupName="admin",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"CodeMismatchException", "ExpiredCodeException"}:
            raise HTTPException(status_code=400, detail="Invalid or expired confirmation code") from exc
        if code == "UserNotFoundException":
            raise HTTPException(status_code=404, detail="No account found for this email") from exc
        raise HTTPException(status_code=503, detail="Confirmation failed") from exc

    return {"message": "Email confirmed — you can sign in now", "email": payload.email}


@router.post("/resend-code")
async def resend_code(payload: ResendRequest) -> dict:
    if not settings.user_pool_client_id:
        raise HTTPException(status_code=503, detail="Registration not configured")

    client = _cognito_client()
    try:
        client.resend_confirmation_code(
            ClientId=settings.user_pool_client_id,
            Username=payload.email,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UserNotFoundException":
            raise HTTPException(status_code=404, detail="No account found for this email") from exc
        raise HTTPException(status_code=503, detail="Could not resend code") from exc

    return {"message": "Confirmation code sent", "email": payload.email}


@router.post("/activate")
async def activate_without_code(payload: LoginRequest) -> dict:
    """Activate account when Cognito verification email was not delivered."""
    if not settings.user_pool_id or not settings.user_pool_client_id:
        raise HTTPException(status_code=503, detail="Registration not configured")
    if not payload.email or not payload.password:
        raise HTTPException(status_code=400, detail="Email and password required")

    client = _cognito_client()
    try:
        client.initiate_auth(
            ClientId=settings.user_pool_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": payload.email, "PASSWORD": payload.password},
        )
        return {"message": "Account already active — sign in below", "email": payload.email}
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code != "UserNotConfirmedException":
            if code in {"NotAuthorizedException", "UserNotFoundException"}:
                raise HTTPException(status_code=401, detail="Invalid email or password") from exc
            raise HTTPException(status_code=503, detail="Activation unavailable") from exc

    try:
        client.admin_confirm_sign_up(UserPoolId=settings.user_pool_id, Username=payload.email)
        client.admin_add_user_to_group(
            UserPoolId=settings.user_pool_id,
            Username=payload.email,
            GroupName="admin",
        )
    except ClientError as exc:
        inner = exc.response.get("Error", {}).get("Code", "")
        if inner == "NotAuthorizedException":
            raise HTTPException(status_code=401, detail="Invalid email or password") from exc
        raise HTTPException(status_code=503, detail="Activation failed") from exc

    return {"message": "Account activated — you can sign in now", "email": payload.email}


@router.get("/me")
async def me(user: dict = Depends(require_admin)) -> dict:
    return {"email": user.get("email"), "auth_type": user.get("auth")}


def admin_required():
    return Depends(require_admin)
