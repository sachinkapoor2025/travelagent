"""Directory / Google Maps lead miner — SerpAPI when configured, free OSM Overpass fallback."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
USER_AGENT = "TravelAI-LeadMiner/1.0"

# lat, lon, market — global travel hubs
MARKET_GEO: list[tuple[str, float, float, str]] = [
    ("travel agency Dubai UAE", 25.2048, 55.2708, "uae"),
    ("travel agents Mumbai India", 19.0760, 72.8777, "india"),
    ("travel agency London UK", 51.5074, -0.1278, "uk"),
    ("travel agents Melbourne Australia", -37.8136, 144.9631, "au"),
    ("travel agency New York", 40.7128, -74.0060, "us"),
]

SERP_QUERIES = [
    ("travel agency Dubai UAE", "uae"),
    ("travel agents Mumbai India", "india"),
    ("travel agency London UK flights", "uk"),
    ("travel agents Melbourne Australia", "au"),
    ("travel agency New York flights", "us"),
]


async def mine_directories(fast: bool = False) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    if settings.serpapi_key and not fast:
        leads.extend(await _mine_serpapi())
    leads.extend(await _mine_osm_overpass(fast=fast))
    return _dedupe_leads(leads)


async def _mine_serpapi() -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for query, market in SERP_QUERIES:
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
                    logger.warning("SerpAPI %s returned %s", query, resp.status_code)
                    continue
                for place in resp.json().get("local_results", [])[:8]:
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
                            "source_detail": f"serpapi:{query}",
                            "travel_intent": "exploring",
                            "opt_in_marketing": True,
                        }
                    )
            except Exception:
                logger.exception("SerpAPI miner failed for %s", query)
    return leads


async def _mine_osm_overpass(fast: bool = False) -> list[dict[str, Any]]:
    """Free travel-agency listings from OpenStreetMap — parallel fetch with hard timeout."""
    headers = {"User-Agent": USER_AGENT}
    markets = MARKET_GEO[:2] if fast else MARKET_GEO
    wait_timeout = 16.0 if fast else 40.0

    async with httpx.AsyncClient(timeout=18.0 if fast else 30.0, headers=headers) as client:
        tasks = [
            asyncio.create_task(_fetch_osm_market(client, label, lat, lon, market))
            for label, lat, lon, market in markets
        ]
        done, pending = await asyncio.wait(tasks, timeout=wait_timeout)
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

    return [lead for lead in leads if lead.get("phone")]


async def _fetch_osm_market(
    client: httpx.AsyncClient,
    label: str,
    lat: float,
    lon: float,
    market: str,
) -> list[dict[str, Any]]:
    query = (
        f"[out:json][timeout:15];("
        f'node["office"="travel_agency"](around:35000,{lat},{lon});'
        f'node["shop"="travel_agency"](around:35000,{lat},{lon});'
        f'node["tourism"="travel_agency"](around:35000,{lat},{lon});'
        f");out body 15;"
    )
    leads: list[dict[str, Any]] = []
    try:
        resp = None
        for base_url in OVERPASS_URLS:
            resp = await client.get(base_url, params={"data": query})
            if resp.status_code == 200:
                break
            if resp.status_code == 429:
                await asyncio.sleep(1.0)
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

    if market == "uae":
        if cleaned.startswith("+971") and len(cleaned) >= 12:
            return cleaned[:13]
        if cleaned.startswith("971") and len(cleaned) >= 12:
            return "+" + cleaned[:12]
        if cleaned.startswith("0") and len(cleaned) >= 9:
            return "+971" + cleaned[1:10]
        if len(cleaned) == 9 and cleaned[0] in "2456789":
            return "+971" + cleaned

    if market == "india":
        if cleaned.startswith("+91") and len(cleaned) >= 12:
            return cleaned[:13]
        if len(cleaned) == 10 and cleaned[0] in "6789":
            return "+91" + cleaned
        if cleaned.startswith("91") and len(cleaned) == 12:
            return "+" + cleaned

    if market == "uk":
        if cleaned.startswith("+44"):
            return cleaned[:13]
        if cleaned.startswith("44") and len(cleaned) >= 12:
            return "+" + cleaned[:12]
        if cleaned.startswith("0") and 10 <= len(cleaned) <= 11:
            return "+44" + cleaned[1:]

    if market == "au":
        if cleaned.startswith("+61"):
            return cleaned[:12]
        if cleaned.startswith("0") and len(cleaned) >= 9:
            return "+61" + cleaned[1:10]

    if market == "us":
        if cleaned.startswith("+1") and len(cleaned) >= 12:
            return cleaned[:12]
        if len(cleaned) == 10:
            return "+1" + cleaned

    if cleaned.startswith("+") and 10 <= len(cleaned) <= 15:
        return cleaned
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
