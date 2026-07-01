"""Directory / Google Maps lead miner via SerpAPI."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

QUERIES = [
    ("travel agency Dubai UAE", "uae"),
    ("travel agents Mumbai India", "india"),
    ("travel agency London UK flights", "uk"),
    ("travel agents Melbourne Australia", "au"),
    ("travel agency New York flights", "us"),
]


async def mine_directories() -> list[dict[str, Any]]:
    if not settings.serpapi_key:
        return _demo_leads()
    leads: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for query, market in QUERIES:
            try:
                resp = await client.get(
                    "https://serpapi.com/search.json",
                    params={
                        "engine": "google_maps",
                        "q": query,
                        "api_key": settings.serpapi_key,
                        "type": "search",
                    },
                )
                if resp.status_code != 200:
                    continue
                for place in resp.json().get("local_results", [])[:8]:
                    phone = place.get("phone") or ""
                    leads.append(
                        {
                            "name": place.get("title"),
                            "phone": phone.replace(" ", "").replace("-", ""),
                            "location": place.get("address"),
                            "market": market,
                            "source": "directories",
                            "source_detail": f"maps:{query}",
                            "travel_intent": "exploring",
                            "opt_in_marketing": True,
                        }
                    )
            except Exception:
                continue
    return [l for l in leads if l.get("phone")]


def _demo_leads() -> list[dict[str, Any]]:
    return [
        {
            "name": "Directory Lead (configure SERPAPI_KEY)",
            "phone": "",
            "location": "Dubai Marina",
            "market": "uae",
            "source": "directories",
            "source_detail": "demo — add SERPAPI_KEY for live Maps mining",
        }
    ]
