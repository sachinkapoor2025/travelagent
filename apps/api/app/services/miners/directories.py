"""Directory / Google Maps lead miner — SerpAPI when configured, free OSM Overpass fallback."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from app.config import get_settings
from app.services.miners.global_markets import GLOBAL_MARKETS, market_batch

settings = get_settings()
logger = logging.getLogger(__name__)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
USER_AGENT = "TravelAI-LeadMiner/1.0"
MARKETS_PER_PASS = 6


async def mine_directories(fast: bool = False) -> list[dict[str, Any]]:
    leads, _, _, _ = await mine_directories_batch(cursor=0, import_limit=30 if fast else 150)
    return leads


async def mine_directories_batch(
    cursor: int = 0,
    import_limit: int = 150,
) -> tuple[list[dict[str, Any]], int, bool, int]:
    """Fetch B2B agency leads for a slice of global markets."""
    total_markets = len(GLOBAL_MARKETS)
    leads: list[dict[str, Any]] = []
    next_cursor = cursor
    complete = cursor >= total_markets

    if settings.serpapi_key and cursor == 0:
        leads.extend(await _mine_serpapi_global())

    if not complete:
        batch_markets, next_cursor, complete = market_batch(cursor, MARKETS_PER_PASS)
        osm_leads = await _mine_osm_markets(batch_markets)
        leads.extend(osm_leads)

    unique = _dedupe_leads(leads)[:import_limit]
    return unique, next_cursor, complete, total_markets


async def _mine_serpapi_global() -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    if not settings.serpapi_key:
        return leads
    queries = [(label, market) for label, _, _, market in GLOBAL_MARKETS[:12]]
    async with httpx.AsyncClient(timeout=30.0) as client:
        for query, market in queries:
            try:
                resp = await client.get(
                    "https://serpapi.com/search.json",
                    params={
                        "engine": "google_maps",
                        "q": f"travel agency {query}",
                        "api_key": settings.serpapi_key,
                        "type": "search",
                    },
                )
                if resp.status_code != 200:
                    continue
                for place in resp.json().get("local_results", [])[:6]:
                    phone = _normalize_phone(place.get("phone") or "", market)
                    if not phone:
                        continue
                    leads.append(
                        {
                            "name": place.get("title"),
                            "phone": phone,
                            "location": place.get("address"),
                            "market": market,
                            "source": "directories",
                            "source_detail": f"google_maps:{query}",
                            "lead_segment": "b2b",
                            "travel_intent": "exploring",
                            "opt_in_marketing": True,
                        }
                    )
            except Exception:
                logger.exception("SerpAPI miner failed for %s", query)
    return leads


async def _mine_osm_markets(markets: list[tuple[str, float, float, str]]) -> list[dict[str, Any]]:
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=25.0, headers=headers) as client:
        tasks = [
            asyncio.create_task(_fetch_osm_market(client, label, lat, lon, market))
            for label, lat, lon, market in markets
        ]
        done, pending = await asyncio.wait(tasks, timeout=120.0)
        for task in pending:
            task.cancel()
        leads: list[dict[str, Any]] = []
        for task in done:
            try:
                batch = task.result()
                if batch:
                    leads.extend(batch)
            except Exception as exc:
                logger.warning("OSM batch error: %s", exc)
        return leads


async def _fetch_osm_market(
    client: httpx.AsyncClient,
    label: str,
    lat: float,
    lon: float,
    market: str,
) -> list[dict[str, Any]]:
    query = (
        f"[out:json][timeout:20];("
        f'node["office"="travel_agency"](around:40000,{lat},{lon});'
        f'node["shop"="travel_agency"](around:40000,{lat},{lon});'
        f'node["tourism"="travel_agency"](around:40000,{lat},{lon});'
        f'way["office"="travel_agency"](around:40000,{lat},{lon});'
        f");out body 20;"
    )
    leads: list[dict[str, Any]] = []
    try:
        resp = None
        for base_url in OVERPASS_URLS:
            resp = await client.get(base_url, params={"data": query})
            if resp.status_code == 200:
                break
            if resp.status_code == 429:
                await asyncio.sleep(1.5)
        if not resp or resp.status_code != 200:
            logger.warning("Overpass %s returned %s", label, resp.status_code if resp else "none")
            return leads
        for element in resp.json().get("elements", []):
            lead = _osm_element_to_lead(element, market, label)
            if lead:
                leads.append(lead)
    except Exception:
        logger.exception("OSM Overpass miner failed for %s", label)
    return leads


def _osm_element_to_lead(element: dict[str, Any], market: str, label: str) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    name = tags.get("name") or tags.get("brand")
    if not name:
        return None

    raw_phone = tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile") or ""
    phone = _normalize_phone(raw_phone, market)
    if not phone:
        return None

    location_parts = [
        tags.get("addr:street"),
        tags.get("addr:city") or tags.get("addr:city:en"),
        tags.get("addr:country"),
    ]
    location = ", ".join(p for p in location_parts if p)

    return {
        "name": name,
        "phone": phone,
        "location": location or label,
        "market": market,
        "source": "directories",
        "source_detail": f"osm:{label}",
        "lead_segment": "b2b",
        "travel_intent": "exploring",
        "opt_in_marketing": True,
    }


def _normalize_phone(raw: str, market: str) -> str:
    if not raw:
        return ""
    cleaned = re.sub(r"[^\d+]", "", str(raw).strip())
    if not cleaned or len(cleaned) > 15:
        return ""

    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    if market == "india" and cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]

    market_prefixes = {
        "uae": "+971",
        "india": "+91",
        "uk": "+44",
        "us": "+1",
        "au": "+61",
        "ca": "+1",
        "sg": "+65",
        "hk": "+852",
        "jp": "+81",
        "kr": "+82",
        "fr": "+33",
        "de": "+49",
        "nl": "+31",
        "it": "+39",
        "es": "+34",
        "tr": "+90",
        "eg": "+20",
        "za": "+27",
        "ke": "+254",
        "sa": "+966",
        "qa": "+974",
        "kw": "+965",
        "om": "+968",
        "il": "+972",
        "br": "+55",
        "mx": "+52",
        "ar": "+54",
        "nz": "+64",
        "th": "+66",
        "my": "+60",
        "id": "+62",
        "ph": "+63",
    }

    prefix = market_prefixes.get(market)
    if prefix and cleaned.startswith(prefix.lstrip("+")):
        return "+" + cleaned if not cleaned.startswith("+") else cleaned
    if prefix and cleaned.startswith("0") and len(cleaned) >= 9:
        return prefix + cleaned[1:]

    if cleaned.startswith("+") and 10 <= len(cleaned) <= 15:
        return cleaned
    if market == "india" and len(cleaned) == 10 and cleaned[0] in "6789":
        return "+91" + cleaned
    if market == "us" and len(cleaned) == 10:
        return "+1" + cleaned
    return ""


def _dedupe_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for lead in leads:
        key = lead.get("phone") or lead.get("name") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(lead)
    return unique
