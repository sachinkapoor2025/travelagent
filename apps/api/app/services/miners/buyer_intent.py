"""B2C buyer intent detection — shared across Telegram, Reddit RSS, Twitter."""

from __future__ import annotations

import hashlib
import re
from typing import Optional

BUYER_INTENT_KEYWORDS = [
    "flight", "ticket", "travel agent", "book karna", "jane ka",
    "kitna hai", "rate kya hai", "koi agent hai",
    "cheap flight", "sasta ticket", "dubai to", "india to",
    "london to", "sydney to", "melbourne to", "toronto",
    "need ticket", "urgent flight", "visa flight",
    "anyone know", "recommend agent", "good agent",
    "flight price", "best rate", "book flight",
    "need flight", "looking for flight", "fly to", "ticket to",
    "ticket chahiye", "flight se", "flight ka", "flight lena",
]

DEAL_EXCLUDE_KEYWORDS = [
    "check link", "book now", "limited offer", "sale",
    "promo", "click here", "subscribe", "join channel",
    "our website", "contact us for deals", "best deals",
    "flash sale", "roundtrip from", "limited time",
]

BUYER_INTENT_RE = re.compile(
    "|".join(re.escape(k) for k in BUYER_INTENT_KEYWORDS),
    re.I,
)
DEAL_EXCLUDE_RE = re.compile(
    "|".join(re.escape(k) for k in DEAL_EXCLUDE_KEYWORDS),
    re.I,
)
PHONE_RE = re.compile(r"(\+?\d{10,14})")

GROUP_MARKET_MAP: dict[str, str] = {
    "indiansindubai": "uae",
    "dubaiindians": "uae",
    "keralites_uae": "uae",
    "nri_dubai_group": "uae",
    "indians_in_uae": "uae",
    "pakistan_uae_community": "uae",
    "dubai_expats_community": "uae",
    "indians_in_london": "uk",
    "uk_desi_community": "uk",
    "indians_in_australia": "au",
    "indian_expats_sydney": "au",
    "nri_usa_community": "us",
}

SUBREDDIT_MARKET_MAP: dict[str, str] = {
    "dubai": "uae",
    "uae": "uae",
    "expats": "uae",
    "india": "india",
    "unitedkingdom": "uk",
    "australia": "au",
    "newjersey": "us",
    "nyc": "us",
    "chicago": "us",
    "travel": "global",
}


def stable_lead_id(prefix: str, key: str) -> str:
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def has_buyer_intent(text: str) -> bool:
    return bool(text and BUYER_INTENT_RE.search(text))


def is_deal_broadcast(text: str) -> bool:
    if not text:
        return True
    if DEAL_EXCLUDE_RE.search(text):
        return True
    lower = text.lower()
    if "best deals on hotels" in lower or "travel deals -" in lower:
        return True
    return False


def passes_buyer_filter(text: str) -> bool:
    """True when post looks like a buyer asking, not a deal broadcast."""
    if not text or len(text.strip()) < 12:
        return False
    if not has_buyer_intent(text):
        return False
    if is_deal_broadcast(text):
        return False
    return True


def extract_phone(text: str) -> str:
    m = PHONE_RE.search(text or "")
    return m.group(1) if m else ""


def market_from_group(group: str) -> str:
    key = group.lower().lstrip("@")
    if key in GROUP_MARKET_MAP:
        return GROUP_MARKET_MAP[key]
    for fragment, market in GROUP_MARKET_MAP.items():
        if fragment in key:
            return market
    return "global"


def market_from_subreddit(name: str) -> str:
    key = (name or "").lower().lstrip("r/")
    for fragment, market in SUBREDDIT_MARKET_MAP.items():
        if fragment in key:
            return market
    return "global"


def market_from_text(text: str, default: str = "global") -> str:
    lower = (text or "").lower()
    rules = [
        (("dubai", "uae", "abu dhabi", "sharjah"), "uae"),
        (("india", "mumbai", "delhi", "bangalore", "chennai"), "india"),
        (("london", " uk ", "manchester"), "uk"),
        (("sydney", "melbourne", "australia"), "au"),
        (("new york", "nyc", "chicago", "toronto", "usa"), "us"),
    ]
    for keywords, market in rules:
        if any(k in lower for k in keywords):
            return market
    return default


def first_name_only(name: Optional[str]) -> str:
    if not name:
        return "—"
    return str(name).split()[0][:40]
