"""Reddit lead miner — B2C travel intent (requires Reddit API credentials since 2024)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SUBREDDITS = [
    "travel", "solotravel", "Flights", "awardtravel", "shoestring", "digitalnomad",
    "dubai", "UAE", "abudhabi", "india", "indiatravel", "solotravelindia",
    "uktravel", "AskUK", "australia", "TravelHacks", "JapanTravel", "ThailandTourism",
    "Singapore", "europe", "Expats", "IWantOut", "familytravel", "TravelDeals",
    "VisaQuestions",
]

SEARCH_QUERIES = [
    "need flight",
    "looking for ticket",
    "book flight help",
    "visa travel",
    "honeymoon package",
    "cheap flights dubai",
    "india to uae flight",
]

TRAVEL_KW = re.compile(
    r"\b(flight|fly|flying|ticket|visa|hotel|package|itinerary|travel|trip|holiday|vacation|"
    r"booking|honeymoon|backpack|airfare|need|looking|help)\b",
    re.I,
)
PHONE_RE = re.compile(r"(\+?\d{10,14})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_last_warning: str | None = None


def reddit_setup_warning() -> str | None:
    return _last_warning


async def _reddit_token(client: httpx.AsyncClient) -> str | None:
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        return None
    auth = (settings.reddit_client_id, settings.reddit_client_secret)
    resp = await client.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=auth,
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": settings.reddit_user_agent},
    )
    if resp.status_code != 200:
        logger.warning("Reddit OAuth failed: %s", resp.status_code)
        return None
    return resp.json().get("access_token")


def _post_to_lead(post: dict[str, Any], sub: str) -> dict[str, Any] | None:
    title = post.get("title", "")
    body = post.get("selftext", "")
    text = f"{title}\n{body}"
    if not TRAVEL_KW.search(text):
        return None
    phone_match = PHONE_RE.search(text)
    email_match = EMAIL_RE.search(text)
    permalink = post.get("permalink", "")
    post_id = post.get("id", "")
    return {
        "name": post.get("author"),
        "phone": phone_match.group(1) if phone_match else "",
        "email": email_match.group(0) if email_match else None,
        "origin": _guess_route(text)[0],
        "destination": _guess_route(text)[1],
        "departure_date": _extract_date(text),
        "passengers": _extract_passengers(text),
        "market": _market_for_sub(sub),
        "source": "reddit",
        "source_detail": f"r/{sub} · {permalink}",
        "external_id": f"reddit:{post_id}",
        "lead_segment": "b2c",
        "travel_intent": "researching",
        "notes": text[:500].strip(),
        "opt_in_marketing": True,
    }


async def mine_reddit(
    limit_per_sub: int = 25,
    subreddit_offset: int = 0,
    max_subreddits: int = 8,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Mine B2C Reddit posts via OAuth API."""
    global _last_warning
    leads: list[dict[str, Any]] = []
    subs = SUBREDDITS[subreddit_offset : subreddit_offset + max_subreddits]
    next_offset = subreddit_offset + len(subs)
    complete = next_offset >= len(SUBREDDITS)

    if not subs:
        return [], next_offset, True

    if not settings.reddit_client_id or not settings.reddit_client_secret:
        _last_warning = (
            "Reddit API blocked without credentials. Add REDDIT_CLIENT_ID and "
            "REDDIT_CLIENT_SECRET to GitHub Secrets, redeploy, then Reset + Fetch B2C."
        )
        logger.warning(_last_warning)
        return [], next_offset, complete

    headers = {"User-Agent": settings.reddit_user_agent}
    async with httpx.AsyncClient(timeout=30.0) as client:
        token = await _reddit_token(client)
        if not token:
            _last_warning = "Reddit OAuth token failed — check REDDIT_CLIENT_ID/SECRET."
            return [], next_offset, complete
        headers["Authorization"] = f"Bearer {token}"
        base = "https://oauth.reddit.com"

        for sub in subs:
            try:
                resp = await client.get(
                    f"{base}/r/{sub}/new",
                    headers=headers,
                    params={"limit": limit_per_sub},
                )
                if resp.status_code != 200:
                    logger.warning("Reddit r/%s returned %s", sub, resp.status_code)
                    continue
                for child in resp.json().get("data", {}).get("children", []):
                    lead = _post_to_lead(child.get("data", {}), sub)
                    if lead:
                        leads.append(lead)
            except Exception:
                logger.exception("Reddit subreddit fetch failed for r/%s", sub)

        if subreddit_offset == 0:
            for query in SEARCH_QUERIES[:4]:
                try:
                    resp = await client.get(
                        f"{base}/search",
                        headers=headers,
                        params={"q": query, "sort": "new", "limit": 15, "t": "month"},
                    )
                    if resp.status_code != 200:
                        continue
                    for child in resp.json().get("data", {}).get("children", []):
                        post = child.get("data", {})
                        sub = post.get("subreddit", "travel")
                        lead = _post_to_lead(post, sub)
                        if lead:
                            leads.append(lead)
                except Exception:
                    logger.exception("Reddit search failed for %s", query)

    _last_warning = None if leads else "Reddit connected but no matching travel posts in this batch."
    filtered = _dedupe(leads)
    return filtered, next_offset, complete


def _dedupe(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for lead in leads:
        key = lead.get("external_id") or lead.get("source_detail") or ""
        if key and key not in seen:
            seen.add(key)
            out.append(lead)
    return out


def _guess_route(text: str) -> tuple[str | None, str | None]:
    lower = text.lower()
    cities = {
        "dubai": "DXB", "delhi": "DEL", "mumbai": "BOM", "london": "LHR",
        "melbourne": "MEL", "sydney": "SYD", "new york": "JFK", "singapore": "SIN",
        "bangkok": "BKK", "tokyo": "NRT", "paris": "CDG", "frankfurt": "FRA",
        "toronto": "YYZ", "los angeles": "LAX", "istanbul": "IST", "bali": "DPS",
    }
    found = [code for name, code in cities.items() if name in lower]
    if len(found) >= 2:
        return found[0], found[1]
    if len(found) == 1:
        return None, found[0]
    return None, None


def _market_for_sub(sub: str) -> str:
    mapping = {
        "india": "india", "indiatravel": "india", "solotravelindia": "india",
        "dubai": "uae", "uae": "uae", "abudhabi": "uae",
        "uktravel": "uk", "askuk": "uk", "australia": "au",
        "japantravel": "jp", "thailandtourism": "th", "singapore": "sg",
    }
    return mapping.get(sub.lower(), "global")


def _extract_date(text: str) -> str | None:
    match = re.search(
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
        r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2})\b",
        text,
        re.I,
    )
    return match.group(1) if match else None


def _extract_passengers(text: str) -> int:
    match = re.search(r"\b(\d)\s*(?:pax|passengers|people|adults|travellers|travelers)\b", text, re.I)
    return int(match.group(1)) if match else 1
