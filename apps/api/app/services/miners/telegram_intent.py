"""Classify Telegram content as callable consumer intent vs promotional deals."""

from __future__ import annotations

import hashlib
import re

CONSUMER_INTENT_RE = re.compile(
    r"\b("
    r"looking for|need (?:a |help with )?(?:flight|ticket|visa|hotel|package)|"
    r"want to (?:book|fly|travel)|anyone (?:know|recommend|suggest)|"
    r"can someone|please help|help me|how much|quote for|planning (?:a )?trip|"
    r"urgent|any advice|recommendation|suggest (?:a |me )|"
    r"i need|we need|searching for|trying to book"
    r")\b",
    re.I,
)

PROMO_DEAL_RE = re.compile(
    r"\b("
    r"deal|deals|flash sale|limited time|book now|click here|promo|promotion|"
    r"discount|\d+\s*%\s*off|round\s*trip|roundtrip|best price|lowest fare|"
    r"offer ends|use code|subscribe|join our|travel tips|travel hacks|"
    r"hotels?, flights and|best deals on"
    r")\b",
    re.I,
)

BROADCAST_CHANNEL_RE = re.compile(
    r"^@\w+:\s*(travel deals|best deals|flight deals|hotels?, flights)",
    re.I,
)

TRAVEL_QUESTION_RE = re.compile(
    r"\b(flight|ticket|visa|hotel|package|travel|trip|booking)\b.*\?",
    re.I,
)


def stable_digest(value: str, digits: int = 12) -> str:
    """Process-stable hash (Python hash() randomizes per Lambda cold start)."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return str(int(digest[:16], 16) % (10**digits)).zfill(digits)


def classify_telegram_lead(
    text: str,
    *,
    from_bot_user: bool = False,
    has_real_phone: bool = False,
    is_channel_preview: bool = False,
) -> tuple[bool, str]:
    """
    Return (call_ready, reason).
    Callable = real person asking for travel help, not a channel broadcasting deals.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return False, "empty"

    if has_real_phone and CONSUMER_INTENT_RE.search(cleaned):
        return True, "phone_and_intent"

    if from_bot_user and not is_channel_preview:
        if PROMO_DEAL_RE.search(cleaned) and not CONSUMER_INTENT_RE.search(cleaned):
            return False, "bot_promo"
        if CONSUMER_INTENT_RE.search(cleaned) or has_real_phone:
            return True, "bot_user_message"
        if len(cleaned) > 40 and TRAVEL_QUESTION_RE.search(cleaned):
            return True, "bot_travel_question"
        return False, "bot_low_intent"

    if is_channel_preview:
        if CONSUMER_INTENT_RE.search(cleaned):
            return True, "channel_consumer_intent"
        if PROMO_DEAL_RE.search(cleaned):
            return False, "channel_deal"
        if BROADCAST_CHANNEL_RE.search(cleaned):
            return False, "channel_broadcast"
        return False, "channel_no_intent"

    return False, "unknown"

