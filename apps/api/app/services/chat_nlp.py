"""Natural-language understanding for Sarah chat — works with or without OpenAI."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.travel_tools import execute_tool

CITY_ALIASES: dict[str, str] = {
    "dubai": "DXB",
    "dxb": "DXB",
    "delhi": "DEL",
    "new delhi": "DEL",
    "del": "DEL",
    "mumbai": "BOM",
    "bombay": "BOM",
    "bom": "BOM",
    "abu dhabi": "AUH",
    "auh": "AUH",
    "sharjah": "SHJ",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "chennai": "MAA",
    "hyderabad": "HYD",
    "kolkata": "CCU",
    "melbourne": "MEL",
    "mel": "MEL",
    "sydney": "SYD",
    "london": "LHR",
    "singapore": "SIN",
    "bangkok": "BKK",
    "istanbul": "IST",
    "doha": "DOH",
    "riyadh": "RUH",
    "jeddah": "JED",
    "muscat": "MCT",
    "toronto": "YYZ",
    "paris": "CDG",
    "amsterdam": "AMS",
    "frankfurt": "FRA",
    "kochi": "COK",
    "goa": "GOI",
    "jaipur": "JAI",
    "ahmedabad": "AMD",
    "pune": "PNQ",
    "lucknow": "LKO",
    "islamabad": "ISB",
    "karachi": "KHI",
    "lahore": "LHE",
}

MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

IATA_TO_CITY: dict[str, str] = {
    "DXB": "Dubai",
    "DEL": "Delhi",
    "BOM": "Mumbai",
    "AUH": "Abu Dhabi",
    "BLR": "Bangalore",
    "MAA": "Chennai",
    "MEL": "Melbourne",
    "LHR": "London",
    "SIN": "Singapore",
    "BKK": "Bangkok",
}


def resolve_city(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", text).strip().lower()
    if not cleaned:
        return None
    if cleaned.upper() in IATA_TO_CITY:
        return cleaned.upper()
    if cleaned in CITY_ALIASES:
        return CITY_ALIASES[cleaned]
    for name, code in CITY_ALIASES.items():
        if name in cleaned or cleaned in name:
            return code
    if len(cleaned) == 3 and cleaned.isalpha():
        return cleaned.upper()
    return None


def parse_date(text: str, reference: Optional[datetime] = None) -> Optional[str]:
    ref = reference or datetime.now(timezone.utc)

    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso:
        return iso.group(0)

    dmy = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if dmy:
        d, m, y = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        return f"{y:04d}-{m:02d}-{d:02d}"

    month_pattern = "|".join(MONTHS.keys())
    patterns = [
        rf"\b(\d{{1,2}})\s+({month_pattern})\s*(20\d{{2}})?\b",
        rf"\b({month_pattern})\s+(\d{{1,2}})\s*(20\d{{2}})?\b",
        rf"(?:on|date\s+is|departure\s+date\s+is|travel\s+on)\s+(\d{{1,2}})\s+({month_pattern})\s*(20\d{{2}})?",
    ]
    lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lower)
        if not match:
            continue
        groups = match.groups()
        if groups[0].isdigit():
            day = int(groups[0])
            month_name = groups[1]
            year = int(groups[2]) if len(groups) > 2 and groups[2] else ref.year
        else:
            month_name = groups[0]
            day = int(groups[1])
            year = int(groups[2]) if len(groups) > 2 and groups[2] else ref.year
        month = MONTHS.get(month_name)
        if not month:
            continue
        try:
            candidate = datetime(year, month, day, tzinfo=timezone.utc)
            if not groups[-1] and candidate.date() < ref.date():
                candidate = datetime(year + 1, month, day, tzinfo=timezone.utc)
            return candidate.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_from_text(text: str) -> dict[str, Any]:
    lower = text.lower()
    found: dict[str, Any] = {}

    for word, code in {
        "english": "en",
        "arabic": "ar",
        "hindi": "hi",
        "urdu": "ur",
    }.items():
        if re.search(rf"\b{word}\b", lower):
            found["language"] = code
            break

    dest_patterns = [
        r"destination\s+is\s+([a-zA-Z\s]{2,30}?)(?:\s+(?:origin|and|date|on|from)|$|[,.])",
        r"(?:flight|fly|flying|travel|going)\s+to\s+([a-zA-Z\s]{2,30}?)(?:\s+(?:on|from|origin|date|and)|$|[,.])",
        r"need\s+(?:a\s+)?flight\s+to\s+([a-zA-Z\s]{2,30}?)(?:\s+(?:on|from|origin|date|and)|$|[,.])",
        r"\bto\s+([a-zA-Z\s]{2,25}?)(?:\s+on\s+\d|\s+from\s|$|[,.])",
    ]
    for pattern in dest_patterns:
        match = re.search(pattern, lower)
        if match:
            code = resolve_city(match.group(1))
            if code:
                found["destination"] = code
                break

    origin_patterns = [
        r"origin\s+is\s+([a-zA-Z\s]{2,30}?)(?:\s+(?:destination|and|date|on|to)|$|[,.])",
        r"(?:flying|travel|depart(?:ing|ure)?)\s+from\s+([a-zA-Z\s]{2,30}?)(?:\s+(?:on|to|destination|date|and)|$|[,.])",
        r"\bfrom\s+([a-zA-Z\s]{2,25}?)(?:\s+on\s+\d|\s+to\s|$|[,.])",
    ]
    for pattern in origin_patterns:
        match = re.search(pattern, lower)
        if match:
            code = resolve_city(match.group(1))
            if code:
                found["origin"] = code
                break

    date = parse_date(text)
    if date:
        found["departure_date"] = date

    pax = re.search(r"(\d+)\s+(?:passenger|passengers|pax|people|traveller|travelers)", lower)
    if pax:
        found["passengers"] = int(pax.group(1))

    return found


def merge_travel_context(session: dict[str, Any]) -> dict[str, Any]:
    """Accumulate origin, destination, dates, and language across the whole conversation."""
    for msg in session.get("messages", []):
        if msg.get("role") != "user":
            continue
        for key, value in extract_from_text(msg["content"]).items():
            if value is not None and value != "":
                session[key] = value
    return session


def has_flight_intent(session: dict[str, Any], message: str = "") -> bool:
    lower = message.lower()
    keywords = (
        "flight",
        "fly",
        "flying",
        "ticket",
        "airport",
        "airline",
        "pnr",
        "baggage",
        "stopover",
    )
    if any(k in lower for k in keywords):
        return True
    if session.get("origin") or session.get("destination"):
        return True
    return bool(session.get("last_search"))


def has_hotel_intent(message: str) -> bool:
    lower = message.lower()
    return any(k in lower for k in ("hotel", "stay", "resort", "accommodation", "room"))


def city_label(code: Optional[str]) -> str:
    if not code:
        return "your destination"
    return IATA_TO_CITY.get(code.upper(), code.upper())


def format_flight_offers(session: dict[str, Any], offers: list[dict[str, Any]]) -> str:
    origin = city_label(session.get("origin"))
    dest = city_label(session.get("destination"))
    date = session.get("departure_date", "")
    if not offers:
        return (
            f"I searched {origin} → {dest} for {date} but couldn't find live seats right now. "
            "Would you like nearby dates or a different airport?"
        )
    lines = [
        f"Here are the best options I found for {origin} → {dest} on {date}:",
        "",
    ]
    for idx, offer in enumerate(offers[:5], start=1):
        summary = offer.get("summary") or offer.get("airline") or "Flight"
        price = offer.get("price", "—")
        currency = offer.get("currency", "AED")
        stops = offer.get("stops", 0)
        stop_txt = "non-stop" if stops == 0 else f"{stops} stop(s)"
        lines.append(f"{idx}. {summary} — {currency} {price} ({stop_txt})")
    lines.extend(
        [
            "",
            "Want me to book one of these, check hotels in "
            f"{city_label(session.get('destination'))}, or search return flights?",
        ]
    )
    return "\n".join(lines)


def build_context_prompt(session: dict[str, Any]) -> str:
    parts = []
    if session.get("origin"):
        parts.append(f"Origin: {session['origin']} ({city_label(session['origin'])})")
    if session.get("destination"):
        parts.append(f"Destination: {session['destination']} ({city_label(session['destination'])})")
    if session.get("departure_date"):
        parts.append(f"Departure date: {session['departure_date']}")
    if session.get("passengers"):
        parts.append(f"Passengers: {session['passengers']}")
    if session.get("language"):
        parts.append(f"Preferred language: {session['language']}")
    if not parts:
        return ""
    return "Known trip details from conversation (do NOT re-ask if already set):\n" + "\n".join(f"- {p}" for p in parts)


def is_language_only(message: str) -> bool:
    lower = message.strip().lower()
    return lower in {"english", "arabic", "hindi", "urdu", "en", "ar", "hi", "ur", "eng"}


async def try_flight_search(session: dict[str, Any], session_id: str) -> tuple[Optional[str], Any]:
    origin = session.get("origin")
    destination = session.get("destination")
    departure_date = session.get("departure_date")
    if not (origin and destination and departure_date):
        return None, None

    result = await execute_tool(
        session_id,
        "search_flights",
        {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "passengers": session.get("passengers", 1),
        },
        session,
    )
    offers = result.get("offers") or []
    session["last_search"] = offers
    session["origin"] = origin
    session["destination"] = destination
    session["departure_date"] = departure_date
    return format_flight_offers(session, offers), result


async def smart_travel_reply(session: dict[str, Any], session_id: str, message: str) -> tuple[str, Any]:
    """Human-like travel replies using parsed conversation context — no OpenAI required."""
    merge_travel_context(session)

    if is_language_only(message):
        lang = session.get("language", "en")
        greetings = {
            "en": "Great, we'll continue in English. Where would you like to fly from and to, and on which date?",
            "ar": "ممتاز! سنتحدث بالعربية. من أين وإلى أين تريد السفر، وفي أي تاريخ؟",
            "hi": "Theek hai, Hindi mein baat karte hain. Aap kahan se kahan aur kis date ko travel karna chahte hain?",
            "ur": "Zabardast! Urdu mein baat karte hain. Aap kahan se kahan aur kis tareekh ko safar karna chahte hain?",
        }
        return greetings.get(lang, greetings["en"]), None

    if has_hotel_intent(message):
        dest = session.get("destination") or "DXB"
        return (
            f"I can find hotels in {city_label(dest)} for you. "
            "Please share check-in and check-out dates, and how many guests."
        ), None

    if has_flight_intent(session, message):
        search_reply, tool_data = await try_flight_search(session, session_id)
        if search_reply:
            return search_reply, tool_data

        origin = session.get("origin")
        destination = session.get("destination")
        date = session.get("departure_date")
        missing = []
        if not origin:
            missing.append("where you're flying from")
        if not destination:
            missing.append("your destination")
        if not date:
            missing.append("your travel date")

        if destination and not origin and not date:
            return (
                f"{city_label(destination)} — great choice! "
                "Which city will you depart from, and what date works for you?"
            ), None
        if origin and destination and not date:
            return (
                f"Got it — {city_label(origin)} to {city_label(destination)}. "
                "What date would you like to travel?"
            ), None
        if origin and date and not destination:
            return (
                f"Flying from {city_label(origin)} on {date}. Where would you like to go?"
            ), None
        if len(missing) == 1:
            return f"Almost there — I just need {missing[0]} to search live flights for you.", None
        return (
            "I'd love to find the best fares for you. "
            f"Please share {', '.join(missing[:-1]) + ' and ' + missing[-1] if len(missing) > 1 else missing[0]}."
        ), None

    msgs = session.get("messages", [])
    if len(msgs) <= 1:
        return (
            "Hi, I'm Sarah from TravelAI. I help with flights, hotels, holiday packages, and itineraries "
            "across UAE and India. Tell me where you'd like to go — for example, "
            "\"Delhi to Dubai on 16 July\"."
        ), None

    return (
        "I'm here for all your travel plans — flights, hotels, packages, visas, and itineraries. "
        "Where would you like to go and when?"
    ), None
