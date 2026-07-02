"""B2C travel-intent leads via SerpAPI Google search (works without Reddit OAuth)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

TRAVEL_SEARCH_QUERIES = [
    "need flight from mumbai to dubai",
    "looking for cheap tickets to dubai",
    "help booking flight india to uae",
    "visa and travel package dubai",
    "solo travel flight deals europe",
    "honeymoon package booking help",
    "last minute flight london to india",
    "travel agent recommendation flights",
]

INTENT_KW = re.compile(
    r"\b(need|looking|help|book|booking|ticket|flight|visa|package|itinerary|quote|price)\b",
    re.I,
)


async def mine_serp_b2c(limit: int = 40) -> list[dict[str, Any]]:
    if not settings.serpapi_key:
        return []
    leads: list[dict[str, Any]] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=25.0) as client:
        for query in TRAVEL_SEARCH_QUERIES:
            try:
                resp = await client.get(
                    "https://serpapi.com/search.json",
                    params={
                        "engine": "google",
                        "q": query,
                        "api_key": settings.serpapi_key,
                        "num": 8,
                    },
                )
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("organic_results", [])[:8]:
                    title = item.get("title") or ""
                    snippet = item.get("snippet") or ""
                    text = f"{title}\n{snippet}"
                    if not INTENT_KW.search(text):
                        continue
                    link = item.get("link") or item.get("displayed_link") or ""
                    if link in seen:
                        continue
                    seen.add(link)
                    leads.append(
                        {
                            "name": title[:80],
                            "phone": "",
                            "location": item.get("source") or "",
                            "origin": None,
                            "destination": _guess_destination(text),
                            "market": _guess_market(text),
                            "source": "reddit" if "reddit" in link else "website",
                            "source_detail": f"serp_b2c:{query} · {link}",
                            "external_id": f"serp:{link}",
                            "lead_segment": "b2c",
                            "travel_intent": "researching",
                            "notes": text[:500],
                            "opt_in_marketing": True,
                        }
                    )
                    if len(leads) >= limit:
                        return leads
            except Exception:
                logger.exception("SerpAPI B2C search failed for %s", query)
    return leads


def _guess_destination(text: str) -> str | None:
    lower = text.lower()
    for name, code in {
        "dubai": "DXB", "mumbai": "BOM", "delhi": "DEL", "london": "LHR",
        "paris": "CDG", "bangkok": "BKK", "singapore": "SIN", "bali": "DPS",
    }.items():
        if name in lower:
            return code
    return None


def _guess_market(text: str) -> str:
    lower = text.lower()
    if any(x in lower for x in ("dubai", "uae", "abu dhabi")):
        return "uae"
    if any(x in lower for x in ("india", "mumbai", "delhi")):
        return "india"
    if "london" in lower or " uk " in lower:
        return "uk"
    return "global"
