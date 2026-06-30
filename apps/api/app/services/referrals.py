"""Referral program — viral growth loop."""

import hashlib
from typing import Any, Optional
from uuid import uuid4

from app.config import get_settings
from app.storage.dynamo import DynamoStore, now_iso

settings = get_settings()

REFERRAL_REWARD_AED = 50
REFERRAL_REWARD_INR = 500


class ReferralService:
    def __init__(self) -> None:
        self.store = DynamoStore(settings.referrals_table)

    def generate_code(self, phone: str) -> str:
        digest = hashlib.sha256(f"{phone}:{settings.secret_key}".encode()).hexdigest()
        return f"TRV-{digest[:8].upper()}"

    async def register(self, phone: str, market: str = "uae") -> dict[str, Any]:
        code = self.generate_code(phone)
        record = {
            "referral_code": code,
            "phone": phone,
            "market": market,
            "referrals_count": 0,
            "rewards_earned": 0,
            "created_at": now_iso(),
        }
        if self.store.enabled:
            self.store.put(f"REFERRER#{phone}", "METADATA", record)
            self.store.put(f"CODE#{code}", "METADATA", {"phone": phone, "market": market})
        currency = "AED" if market == "uae" else "INR"
        reward = REFERRAL_REWARD_AED if market == "uae" else REFERRAL_REWARD_INR
        return {
            "referral_code": code,
            "share_message": (
                f"Book your next trip with TravelAI! Use my code {code} and we both get "
                f"{currency} {reward} off. ✈️"
            ),
            "reward_per_referral": reward,
            "currency": currency,
        }

    async def apply(self, referral_code: str, new_phone: str) -> dict[str, Any]:
        if not self.store.enabled:
            return {"applied": False, "reason": "Referrals not available in local mode"}

        code_record = self.store.get(f"CODE#{referral_code}", "METADATA")
        if not code_record:
            return {"applied": False, "reason": "Invalid referral code"}

        referrer_phone = code_record["phone"]
        if referrer_phone == new_phone:
            return {"applied": False, "reason": "Cannot refer yourself"}

        existing = self.store.get(f"REFERRED#{new_phone}", "METADATA")
        if existing:
            return {"applied": False, "reason": "Already used a referral code"}

        market = code_record.get("market", "uae")
        reward = REFERRAL_REWARD_AED if market == "uae" else REFERRAL_REWARD_INR
        currency = "AED" if market == "uae" else "INR"

        self.store.put(
            f"REFERRED#{new_phone}",
            "METADATA",
            {"referral_code": referral_code, "referrer_phone": referrer_phone, "created_at": now_iso()},
        )

        referrer = self.store.get(f"REFERRER#{referrer_phone}", "METADATA") or {}
        count = int(referrer.get("referrals_count", 0)) + 1
        earned = float(referrer.get("rewards_earned", 0)) + reward
        self.store.update(
            f"REFERRER#{referrer_phone}",
            "METADATA",
            {"referrals_count": count, "rewards_earned": earned},
        )

        return {
            "applied": True,
            "discount": reward,
            "currency": currency,
            "referrer_reward": reward,
        }

    async def stats(self, phone: str) -> Optional[dict[str, Any]]:
        if not self.store.enabled:
            return None
        record = self.store.get(f"REFERRER#{phone}", "METADATA")
        if not record:
            return None
        market = record.get("market", "uae")
        return {
            "referral_code": record.get("referral_code"),
            "referrals_count": record.get("referrals_count", 0),
            "rewards_earned": record.get("rewards_earned", 0),
            "currency": "AED" if market == "uae" else "INR",
        }


referral_service = ReferralService()
