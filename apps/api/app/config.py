"""Application configuration — DynamoDB-only (pay-per-request, no Postgres/RDS)."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TravelAI Agent"
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "change-me-in-production"
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"

    openai_api_key: str = ""

    vapi_api_key: str = ""
    vapi_assistant_id: str = ""
    vapi_webhook_secret: str = ""
    vapi_phone_number_id: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number_uae: str = ""
    twilio_phone_number_india: str = ""
    twilio_whitelist_numbers: str = ""

    duffel_api_token: str = ""
    duffel_env: Literal["test", "live"] = "test"

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "travel-ai-verify-token"
    whatsapp_business_account_id: str = ""

    google_ads_developer_token: str = ""
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_refresh_token: str = ""
    google_ads_customer_id: str = ""

    meta_access_token: str = ""
    meta_ad_account_id: str = ""

    serpapi_key: str = ""

    user_pool_id: str = ""
    user_pool_client_id: str = ""
    portal_api_key: str = ""

    aws_region: str = "ap-south-1"
    aws_access_key_id: str = "local"
    aws_secret_access_key: str = "local"
    dynamodb_endpoint: str = ""  # http://localhost:8001 for local DynamoDB

    storage_backend: Literal["dynamo"] = "dynamo"
    leads_table: str = "travel-ai-leads-dev"
    bookings_table: str = "travel-ai-bookings-dev"
    sessions_table: str = "travel-ai-sessions-dev"
    conversations_table: str = "travel-ai-conversations-dev"
    price_alerts_table: str = "travel-ai-price-alerts-dev"
    events_table: str = "travel-ai-events-dev"
    referrals_table: str = "travel-ai-referrals-dev"
    itineraries_table: str = "travel-ai-itineraries-dev"
    recordings_bucket: str = ""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_from: str = "travel@travelai.com"
    smtp_pass: str = ""
    site_url: str = "http://localhost:8000"

    uae_calling_hours_start: str = "09:00"
    uae_calling_hours_end: str = "18:00"
    uae_timezone: str = "Asia/Dubai"
    india_calling_hours_start: str = "09:00"
    india_calling_hours_end: str = "20:00"
    india_timezone: str = "Asia/Kolkata"
    require_opt_in: bool = True

    lead_callback_delay_seconds: int = 60
    lead_hot_score_threshold: int = 80
    lead_warm_score_threshold: int = 50

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        aliases = {"dev": "development", "prod": "production"}
        normalized = aliases.get(str(value).lower(), value)
        return normalized

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def twilio_whitelist(self) -> set[str]:
        return {n.strip() for n in self.twilio_whitelist_numbers.split(",") if n.strip()}

    @property
    def duffel_base_url(self) -> str:
        return "https://api.duffel.com"

    @property
    def use_dynamo(self) -> bool:
        return True


@lru_cache
def get_settings() -> Settings:
    return Settings()
