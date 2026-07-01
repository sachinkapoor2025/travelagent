"""Reddit lead miner — travel intent posts across global subreddits."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

SUBREDDITS = [
    "dubai", "UAE", "abudhabi", "india", "travel", "solotravel",
    "Flights", "awardtravel", "AusFinance", "AskUK", "expats",
]

TRAVEL_KW = re.compile(
    r"\b(flight|fly|flying|ticket|visa|hotel|package|itinerary|travel|trip|holiday|vacation|dxb|del|bom)\b",
    re.I,
)
PHONE_RE = re.compile(r"(\+?\d{10,14})")


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


async def mine_reddit(limit_per_sub: int = 15) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    headers = {"User-Agent": settings.reddit_user_agent}

    async with httpx.AsyncClient(timeout=25.0) as client:
        token = await _reddit_token(client)
        if token:
            headers["Authorization"] = f"Bearer {token}"
            base = "https://oauth.reddit.com"
        else:
            base = "https://www.reddit.com"

        for sub in SUBREDDITS:
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
                    leads.append(
                        {
                            "name": post.get("author"),
                            "phone": phone_match.group(1) if phone_match else "",
                            "origin": _guess_route(text)[0],
                            "destination": _guess_route(text)[1],
                            "departure_date": _extract_date(text),
                            "market": _market_for_sub(sub),
                            "source": "reddit",
                            "source_detail": f"r/{sub} · {post.get('permalink', '')}",
                            "travel_intent": "researching",
                            "notes": text[:400].strip(),
                            "opt_in_marketing": True,
                        }
                    )
            except Exception:
                continue
    return [l for l in leads if l.get("phone") or l.get("destination")]


def _guess_route(text: str) -> tuple[str | None, str | None]:
    lower = text.lower()
    cities = {
        "dubai": "DXB", "delhi": "DEL", "mumbai": "BOM", "london": "LHR",
        "melbourne": "MEL", "sydney": "SYD", "new york": "JFK", "singapore": "SIN",
    }
    found = [code for name, code in cities.items() if name in lower]
    if len(found) >= 2:
        return found[0], found[1]
    if len(found) == 1:
        return None, found[0]
    return None, None


def _market_for_sub(sub: str) -> str:
    if sub.lower() in {"india", "awardtravel"}:
        return "india"
    if sub.lower() in {"dubai", "uae", "abudhabi"}:
        return "uae"
    if sub.lower() in {"askuk", "expats"}:
        return "uk"
    if sub.lower() in {"ausfinance"}:
        return "au"
    if sub.lower() in {"flights", "solotravel", "travel"}:
        return "us"
    return "uae"


def _extract_date(text: str) -> str | None:
    match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2})\b", text, re.I)
    return match.group(1) if match else None
