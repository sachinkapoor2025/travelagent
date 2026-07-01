"""Reddit lead miner — B2C travel intent posts across global subreddits."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

SUBREDDITS = [
    "travel", "solotravel", "Flights", "awardtravel", "shoestring", "digitalnomad",
    "dubai", "UAE", "abudhabi", "india", "indiatravel", "solotravelindia",
    "uktravel", "AskUK", "AusFinance", "australia", "TravelHacks", "TravelNoPics",
    "JapanTravel", "ThailandTourism", "Singapore", "europe", "Expats", "IWantOut",
    "familytravel", "TravelDeals", "churning", "VisaQuestions",
]

TRAVEL_KW = re.compile(
    r"\b(flight|fly|flying|ticket|visa|hotel|package|itinerary|travel|trip|holiday|vacation|"
    r"dxb|del|bom|lhr|jfk|booking|honeymoon|backpack|airfare)\b",
    re.I,
)
PHONE_RE = re.compile(r"(\+?\d{10,14})")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


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
        return None
    return resp.json().get("access_token")


async def mine_reddit(
    limit_per_sub: int = 20,
    subreddit_offset: int = 0,
    max_subreddits: int = 8,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Mine B2C Reddit posts. Returns leads, next subreddit cursor, complete flag."""
    leads: list[dict[str, Any]] = []
    headers = {"User-Agent": settings.reddit_user_agent}
    subs = SUBREDDITS[subreddit_offset : subreddit_offset + max_subreddits]
    next_offset = subreddit_offset + len(subs)
    complete = next_offset >= len(SUBREDDITS)

    if not subs:
        return [], next_offset, True

    async with httpx.AsyncClient(timeout=25.0) as client:
        token = await _reddit_token(client)
        if token:
            headers["Authorization"] = f"Bearer {token}"
            base = "https://oauth.reddit.com"
        else:
            base = "https://www.reddit.com"

        for sub in subs:
            try:
                resp = await client.get(
                    f"{base}/r/{sub}/new.json",
                    headers=headers,
                    params={"limit": limit_per_sub},
                )
                if resp.status_code != 200:
                    continue
                for child in resp.json().get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = post.get("title", "")
                    body = post.get("selftext", "")
                    text = f"{title}\n{body}"
                    if not TRAVEL_KW.search(text):
                        continue
                    phone_match = PHONE_RE.search(text)
                    email_match = EMAIL_RE.search(text)
                    permalink = post.get("permalink", "")
                    post_id = post.get("id", "")
                    leads.append(
                        {
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
                    )
            except Exception:
                continue
    filtered = [l for l in leads if l.get("phone") or l.get("destination") or l.get("email")]
    return filtered, next_offset, complete


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
        "uktravel": "uk", "askuk": "uk",
        "ausfinance": "au", "australia": "au",
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
