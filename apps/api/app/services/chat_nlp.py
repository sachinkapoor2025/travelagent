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

ORIGIN_STOP = r"(?:\s+(?:and|on|to|date|will|for|,)|\s+\d|$|[,.])"
DEST_STOP = r"(?:\s+(?:from|on|and|date|will|for|,)|\s+\d|$|[,.])"


def resolve_city(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", text).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return None
    if cleaned.upper() in IATA_TO_CITY:
        return cleaned.upper()
    if cleaned in CITY_ALIASES:
        return CITY_ALIASES[cleaned]
    # Longest alias match first (e.g. "new delhi" before "delhi")
    for name in sorted(CITY_ALIASES.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", cleaned):
            return CITY_ALIASES[name]
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
        rf"destination\s+is\s+([a-zA-Z\s]{{2,30}}?){DEST_STOP}",
        rf"(?:flight|fly|flying|travel|going|book(?:ing)?)\s+to\s+([a-zA-Z\s]{{2,30}}?){DEST_STOP}",
        rf"need\s+(?:a\s+)?flight\s+to\s+([a-zA-Z\s]{{2,30}}?){DEST_STOP}",
        rf"\bto\s+([a-zA-Z\s]{{2,25}}?){DEST_STOP}",
    ]
    for pattern in dest_patterns:
        match = re.search(pattern, lower)
        if match:
            code = resolve_city(match.group(1))
            if code:
                found["destination"] = code
                break

    origin_patterns = [
        rf"origin\s+is\s+([a-zA-Z\s]{{2,30}}?){ORIGIN_STOP}",
        rf"(?:flying|fly|travel|depart(?:ing|ure)?)\s+from\s+([a-zA-Z\s]{{2,30}}?){ORIGIN_STOP}",
        rf"\bfrom\s+([a-zA-Z\s]{{2,30}}?){ORIGIN_STOP}",
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

    pax = re.search(r"(\d+)\s+(?:passenger|passengers|pax|people|traveller|travelers|adults?)", lower)
    if pax:
        found["passengers"] = int(pax.group(1))

    return found


def apply_message_to_session(session: dict[str, Any], message: str) -> dict[str, Any]:
    """Merge entities from the latest user message into session context."""
    extracted = extract_from_text(message)
    for key, value in extracted.items():
        if value is not None and value != "":
            session[key] = value

    stripped = message.strip()
    if not stripped or len(stripped.split()) > 6:
        return session

    city = resolve_city(stripped)
    if not city:
        return session

    dest = session.get("destination")
    origin = session.get("origin")
    if dest and not origin and city != dest:
        session["origin"] = city
    elif origin and not dest and city != origin:
        session["destination"] = city
    elif not dest:
        session["destination"] = city
    elif not origin:
        session["origin"] = city
    return session


def merge_travel_context(session: dict[str, Any]) -> dict[str, Any]:
    """Accumulate origin, destination, dates, and language across the whole conversation."""
    for msg in session.get("messages", []):
        if msg.get("role") != "user":
            continue
        apply_message_to_session(session, msg["content"])
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
        "travel",
    )
    if any(k in lower for k in keywords):
        return True
    if session.get("origin") or session.get("destination"):
        return True
    return bool(session.get("last_search"))


def has_hotel_intent(message: str) -> bool:
    lower = message.lower()
    return any(k in lower for k in ("hotel", "stay", "resort", "accommodation", "room"))


def has_booking_intent(message: str) -> bool:
    lower = message.lower().strip()
    patterns = (
        r"\bbook(?:ing)?\b",
        r"\bconfirm(?:ation)?\b",
        r"\bproceed\b",
        r"\breserve\b",
        r"\byes\b.*\bbook",
        r"\bbook\s+it\b",
        r"\bgo\s+ahead\b",
        r"what details",
        r"what (?:info|information) (?:do you|you) need",
        r"details (?:do you|you) need",
        r"\byeds\b.*\bbook",
    )
    return any(re.search(p, lower) for p in patterns)


def wants_new_search(message: str) -> bool:
    lower = message.lower()
    return any(
        k in lower
        for k in (
            "search again",
            "new search",
            "different date",
            "other flights",
            "change date",
            "different route",
            "another flight",
        )
    )


def should_run_flight_search(session: dict[str, Any], message: str) -> bool:
    """Only search when we have full trip details and user isn't booking or re-asking."""
    if has_booking_intent(message):
        return False
    if parse_flight_selection(message, session) is not None:
        return False
    if session.get("booking_step"):
        return False
    if wants_new_search(message):
        return True

    origin = session.get("origin")
    destination = session.get("destination")
    date = session.get("departure_date")
    if not (origin and destination and date):
        return False

    if session.get("last_search"):
        lower = message.lower()
        # Short replies that fill missing info — don't re-search yet
        if len(lower.split()) <= 8 and not any(k in lower for k in ("search", "find", "show", "options", "flights")):
            return False
    return True


def parse_flight_selection(message: str, session: dict[str, Any]) -> Optional[int]:
    lower = message.lower()
    offers = session.get("last_search") or []
    if not offers:
        return None
    subset = offers[:5]

    # Match quoted price e.g. 883
    for match in re.finditer(r"\b(\d{3,5})\b", lower):
        target = int(match.group(1))
        for i, offer in enumerate(subset, start=1):
            try:
                if abs(float(offer.get("price") or 0) - target) <= 30:
                    return i
            except (TypeError, ValueError):
                continue

    # Match stop count e.g. "2 stop" — before generic option numbers
    stop_match = re.search(r"\b(\d+)\s*[-]?\s*stop", lower)
    if stop_match:
        want_stops = int(stop_match.group(1))
        for i, offer in enumerate(subset, start=1):
            if int(offer.get("stops", -1)) == want_stops:
                return i

    if re.search(r"\b(cheapest|budget|lowest)\b", lower):
        cheapest = min(
            range(len(subset)),
            key=lambda i: float(subset[i].get("price") or 999999),
        )
        return cheapest + 1

    if re.search(r"\b(first|1st|direct|non.?stop)\b", lower):
        for i, offer in enumerate(subset, start=1):
            if offer.get("stops", 99) == 0:
                return i
        return 1

    if re.search(r"\b(?:option|number|#)\s*([1-5])\b", lower):
        idx = int(re.search(r"\b(?:option|number|#)\s*([1-5])\b", lower).group(1))
        if 1 <= idx <= len(subset):
            return idx

    if re.search(r"\bbook\s+(?:option\s+)?([1-5])\b", lower):
        idx = int(re.search(r"\bbook\s+(?:option\s+)?([1-5])\b", lower).group(1))
        if 1 <= idx <= len(subset):
            return idx

    # Lone option digit — not when talking about stops
    if "stop" not in lower:
        alone = re.search(r"(?:^|\s)([1-5])(?:\s*$|[,.])", lower)
        if alone:
            idx = int(alone.group(1))
            if 1 <= idx <= len(subset):
                return idx

    if re.search(r"\b(second|2nd)\b", lower) and "stop" not in lower:
        return 2 if len(subset) >= 2 else 1
    if re.search(r"\b(third|3rd)\b", lower):
        return 3 if len(subset) >= 3 else len(subset)

    if has_booking_intent(message) and len(subset) == 1:
        return 1
    return None


def city_label(code: Optional[str]) -> str:
    if not code:
        return "your destination"
    return IATA_TO_CITY.get(code.upper(), code.upper())


def fmt_price(price: Any, currency: str = "AED") -> str:
    try:
        return f"{currency} {int(round(float(price)))}"
    except (TypeError, ValueError):
        return f"{currency} {price}"


def offer_summary(offer: dict[str, Any], index: int) -> str:
    summary = offer.get("summary") or offer.get("airline") or f"Option {index}"
    currency = offer.get("currency", "AED")
    price = fmt_price(offer.get("price", "—"), currency)
    stops = offer.get("stops", 0)
    stop_txt = "non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
    return f"{summary} — {price} ({stop_txt})"


def format_flight_offers(session: dict[str, Any], offers: list[dict[str, Any]]) -> str:
    origin = city_label(session.get("origin"))
    dest = city_label(session.get("destination"))
    date = session.get("departure_date", "")
    if not offers:
        return (
            f"I checked {origin} → {dest} for {date} but nothing's showing live right now. "
            "Happy to try nearby dates or a different airport — just say the word."
        )
    lines = [
        f"Great news — here are the best fares I found for {origin} → {dest} on {date}:",
        "",
    ]
    for idx, offer in enumerate(offers[:5], start=1):
        lines.append(f"{idx}. {offer_summary(offer, idx)}")
    lines.extend(
        [
            "",
            "Which one works for you? Reply with 1, 2, or 3 — or say direct, cheapest, or book option 2 "
            "and I'll take care of the rest.",
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
    if session.get("last_search"):
        parts.append(f"Flight options already shown: {len(session['last_search'])} offers — do NOT search again unless user asks")
    if session.get("booking_step"):
        parts.append(f"Booking in progress — step: {session['booking_step']}")
    if session.get("selected_offer_index"):
        parts.append(f"Selected flight: option {session['selected_offer_index']}")
    if not parts:
        return ""
    return "Known trip details from conversation (do NOT re-ask if already set):\n" + "\n".join(f"- {p}" for p in parts)


def is_language_only(message: str) -> bool:
    lower = message.strip().lower()
    return lower in {"english", "arabic", "hindi", "urdu", "en", "ar", "hi", "ur", "eng"}


def _extract_contact_fields(message: str, session: dict[str, Any]) -> None:
    text = message.strip()

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if email_match:
        session["email"] = email_match.group(0)

    phone_match = re.search(r"(?:\+|=)?(\d{10,15})", text.replace(" ", ""))
    if phone_match:
        digits = phone_match.group(1)
        if digits.startswith("91") and len(digits) >= 12:
            session["phone"] = f"+{digits}"
        elif digits.startswith("971"):
            session["phone"] = f"+{digits}"
        elif len(digits) == 10:
            session["phone"] = f"+91{digits}"
        else:
            session["phone"] = f"+{digits.lstrip('+')}"

    name_match = re.search(
        r"(?:name is|my name is|i am|i'm)\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        text,
        re.I,
    )
    if name_match:
        session["passenger_name"] = name_match.group(1).strip().title()
        return

    # Combined line: "Sachin kapoor +919999598900 email@x.com"
    remainder = text
    if email_match:
        remainder = remainder.replace(email_match.group(0), " ")
    if phone_match:
        remainder = re.sub(r"[+=]?\d{10,15}", " ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip(" ,.-=")
    if remainder and re.match(r"^[A-Za-z][A-Za-z\s'-]{1,40}$", remainder):
        session["passenger_name"] = remainder.title()
        return

    # Standalone name while collecting booking details
    if session.get("booking_step") == "collect_details" and not session.get("passenger_name"):
        cleaned = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "", text)
        cleaned = re.sub(r"[+=]?\d{10,15}", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-=")
        if cleaned and re.match(r"^[A-Za-z][A-Za-z\s'-]{1,40}$", cleaned):
            session["passenger_name"] = cleaned.title()


def booking_flow_reply(session: dict[str, Any], message: str) -> Optional[str]:
    """Handle post-search booking conversation without re-running flight search."""
    offers = session.get("last_search") or []
    if not offers and not session.get("booking_step"):
        return None

    _extract_contact_fields(message, session)

    already_selected = session.get("selected_offer_index")
    changing = bool(re.search(r"\b(option|change|instead|cheapest|direct|\d\s*stop|book)\b", message.lower()))
    selection = None
    if not already_selected or changing:
        selection = parse_flight_selection(message, session)

    if selection:
        session["selected_offer_index"] = selection
        session["booking_step"] = "collect_details"
        offer = offers[selection - 1]
        return (
            f"Perfect choice — {offer_summary(offer, selection)}.\n\n"
            "To lock this in, I just need:\n"
            "• Full name (as on passport)\n"
            "• Mobile number (with country code, e.g. +971…)\n"
            "• Email for the e-ticket\n\n"
            "You can send all three in one message."
        )

    if has_booking_intent(message) or session.get("booking_step"):
        if not session.get("selected_offer_index"):
            session["booking_step"] = "select_flight"
            if len(offers) == 1:
                session["selected_offer_index"] = 1
                session["booking_step"] = "collect_details"
                offer = offers[0]
                return (
                    f"Absolutely — let's book {offer_summary(offer, 1)}.\n\n"
                    "Please share your full name, mobile number, and email and I'll prepare your booking."
                )
            return (
                "Happy to book this for you! Which option would you like — "
                "1 (direct), 2, or 3 (cheapest)? Or say 'direct' or 'cheapest'."
            )

        if session.get("booking_step") == "collect_details":
            missing = []
            if not session.get("passenger_name"):
                missing.append("full name")
            if not session.get("phone"):
                missing.append("mobile number")
            if not session.get("email"):
                missing.append("email")

            if missing:
                return (
                    f"Almost done — I still need your {' and '.join(missing)}. "
                    "Once I have those, I'll send you a secure payment link to confirm."
                )

            idx = session.get("selected_offer_index", 1)
            offer = offers[idx - 1] if offers else {}
            origin = city_label(session.get("origin"))
            dest = city_label(session.get("destination"))
            date = session.get("departure_date", "")
            name = session.get("passenger_name")
            phone = session.get("phone")
            email = session.get("email")
            session["booking_step"] = "ready"
            return (
                f"Thanks {name}! Here's what I have:\n\n"
                f"✈ {origin} → {dest} on {date}\n"
                f"🎫 {offer_summary(offer, idx)}\n"
                f"📱 {phone} · ✉ {email}\n\n"
                "I'll generate your payment link and PNR shortly. "
                "If anything needs changing, just tell me."
            )

    return None


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
    session.pop("booking_step", None)
    session.pop("selected_offer_index", None)
    return format_flight_offers(session, offers), result


async def smart_travel_reply(session: dict[str, Any], session_id: str, message: str) -> tuple[str, Any]:
    """Human-like travel replies using parsed conversation context — no OpenAI required."""
    apply_message_to_session(session, message)

    booking = booking_flow_reply(session, message)
    if booking:
        return booking, None

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
            "Share check-in and check-out dates, and how many guests."
        ), None

    if has_flight_intent(session, message):
        if should_run_flight_search(session, message):
            search_reply, tool_data = await try_flight_search(session, session_id)
            if search_reply:
                return search_reply, tool_data

        origin = session.get("origin")
        destination = session.get("destination")
        date = session.get("departure_date")

        if session.get("last_search"):
            return (
                "I've already pulled up the fares above. "
                "Tell me which option you'd like (1, 2, or 3), or say book the direct flight "
                "and I'll collect your details."
            ), None

        missing = []
        if not origin:
            missing.append("departure city")
        if not destination:
            missing.append("destination")
        if not date:
            missing.append("travel date")

        if destination and not origin and not date:
            return (
                f"{city_label(destination)} — lovely choice! "
                "Where will you be flying from, and what date suits you?"
            ), None
        if origin and destination and not date:
            return (
                f"Got it — {city_label(origin)} to {city_label(destination)}. "
                "What date would you like to travel?"
            ), None
        if origin and date and not destination:
            return (
                f"Flying from {city_label(origin)} on {date} — where would you like to go?"
            ), None
        if destination and date and not origin:
            return (
                f"Heading to {city_label(destination)} on {date}. "
                "Which city are you departing from?"
            ), None
        if len(missing) == 1:
            return f"Just need your {missing[0]} and I'll search live fares straight away.", None
        return (
            "I'd love to find the best fares for you — "
            f"could you share your {', '.join(missing[:-1]) + ' and ' + missing[-1] if len(missing) > 1 else missing[0]}?"
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
