"""Extract routes, dates, prices, and titles from travel post text."""

from __future__ import annotations

import re
from typing import Any

CITY_TO_IATA: dict[str, str] = {
    "dubai": "DXB", "abu dhabi": "AUH", "sharjah": "SHJ",
    "mumbai": "BOM", "delhi": "DEL", "new delhi": "DEL", "bangalore": "BLR",
    "chennai": "MAA", "hyderabad": "HYD", "kolkata": "CCU", "goa": "GOI",
    "london": "LHR", "manchester": "MAN", "paris": "CDG", "frankfurt": "FRA",
    "amsterdam": "AMS", "rome": "FCO", "madrid": "MAD", "istanbul": "IST",
    "singapore": "SIN", "bangkok": "BKK", "bali": "DPS", "phuket": "HKT",
    "tokyo": "NRT", "osaka": "KIX", "seoul": "ICN", "hong kong": "HKG",
    "melbourne": "MEL", "sydney": "SYD", "auckland": "AKL",
    "new york": "JFK", "los angeles": "LAX", "chicago": "ORD", "toronto": "YYZ",
    "cairo": "CAI", "riyadh": "RUH", "jeddah": "JED", "doha": "DOH",
    "muscat": "MCT", "kuwait": "KWI", "manila": "MNL", "jakarta": "CGK",
    "kuala lumpur": "KUL", "nairobi": "NBO", "cape town": "CPT",
}

IATA_CODES = set(CITY_TO_IATA.values())

FROM_TO_RE = re.compile(
    r"(?:from|depart(?:ing|ure)?(?:\s+from)?)\s+([a-zA-Z\s]{2,30}?)\s+"
    r"(?:to|→|->|-|—)\s+([a-zA-Z\s]{2,30}?)(?:[\s,.]|$|\d)",
    re.I,
)
ARROW_RE = re.compile(
    r"\b([a-zA-Z\s]{2,25}?)\s*(?:→|->|-|—)\s*([a-zA-Z\s]{2,25}?)\b",
    re.I,
)
IATA_PAIR_RE = re.compile(r"\b([A-Z]{3})\s*(?:-|→|->|to)\s*([A-Z]{3})\b")
PRICE_RE = re.compile(
    r"(?:₹|Rs\.?|INR|AED|USD|\$|€|EUR|£|GBP)\s*([\d,]+(?:\.\d{1,2})?)|"
    r"([\d,]+(?:\.\d{1,2})?)\s*(?:AED|USD|INR|EUR|GBP|₹)",
    re.I,
)
DATE_RE = re.compile(
    r"\b("
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+\d{4})?|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,?\s*\d{4})?(?!\s*\d)"
    r")\b",
    re.I,
)
PAX_RE = re.compile(r"\b(\d)\s*(?:pax|passengers?|adults?|travellers?|travelers?|people)\b", re.I)


def parse_travel_text(text: str, channel: str | None = None) -> dict[str, Any]:
    """Parse unstructured travel post/deal text into lead fields."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    lower = cleaned.lower()
    result: dict[str, Any] = {}

    origin, destination = _extract_route(cleaned)
    if origin:
        result["origin"] = origin
    if destination:
        result["destination"] = destination

    dates = DATE_RE.findall(cleaned)
    if dates:
        result["departure_date"] = dates[0]
        if len(dates) > 1:
            result["return_date"] = dates[1]

    price = _extract_price(cleaned)
    if price:
        result["budget_max"] = price

    pax = PAX_RE.search(cleaned)
    if pax:
        result["passengers"] = int(pax.group(1))

    cities = _mentioned_city_names(lower)
    if cities:
        result["location"] = ", ".join(cities[:3])

    title = _extract_title(cleaned)
    if channel:
        ch = channel.lstrip("@")
        result["name"] = f"@{ch}: {title}"[:120] if title else f"@{ch} deal"
    elif title:
        result["name"] = title[:120]

    if any(w in lower for w in ("need", "looking", "help", "anyone", "suggest")):
        result["travel_intent"] = "researching"
    elif any(w in lower for w in ("book", "booking", "confirm", "pay")):
        result["travel_intent"] = "ready_to_book"
    elif price or "deal" in lower:
        result["travel_intent"] = "exploring"

    return result


def _extract_route(text: str) -> tuple[str | None, str | None]:
    m = IATA_PAIR_RE.search(text)
    if m:
        return m.group(1), m.group(2)

    m = FROM_TO_RE.search(text)
    if m:
        o = _city_to_iata(m.group(1).strip())
        d = _city_to_iata(m.group(2).strip())
        if o or d:
            return o, d

    m = ARROW_RE.search(text)
    if m:
        o = _city_to_iata(m.group(1).strip())
        d = _city_to_iata(m.group(2).strip())
        if o or d:
            return o, d

    codes = [c for c in IATA_CODES if re.search(rf"\b{c}\b", text)]
    cities_found = []
    lower = text.lower()
    for city, code in sorted(CITY_TO_IATA.items(), key=lambda x: -len(x[0])):
        if city in lower and code not in cities_found:
            cities_found.append(code)
    if len(cities_found) >= 2:
        return cities_found[0], cities_found[1]
    if len(cities_found) == 1:
        return None, cities_found[0]
    if len(codes) >= 2:
        return codes[0], codes[1]
    if len(codes) == 1:
        return None, codes[0]
    return None, None


def _city_to_iata(raw: str) -> str | None:
    key = raw.lower().strip()
    if key.upper() in IATA_CODES and len(key) == 3:
        return key.upper()
    if key in CITY_TO_IATA:
        return CITY_TO_IATA[key]
    for city, code in CITY_TO_IATA.items():
        if city in key or key in city:
            return code
    return None


def _mentioned_city_names(lower: str) -> list[str]:
    found: list[str] = []
    for city in CITY_TO_IATA:
        if city in lower:
            found.append(city.title())
    return found


def _extract_price(text: str) -> float | None:
    m = PRICE_RE.search(text)
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or "").replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_title(text: str) -> str:
    line = text.split("\n")[0].strip()
    if not line:
        line = text[:100]
    line = re.sub(r"https?://\S+", "", line).strip()
    line = re.sub(r"[^\w\s→\-–—$€£₹,.@#&()+/'\"]", " ", line)
    line = re.sub(r"\s+", " ", line).strip()
    if len(line) > 90:
        line = line[:87] + "…"
    return line or text[:80]
