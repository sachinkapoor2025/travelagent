"""Lightweight multi-agent routing — intent → specialist prompt."""

from typing import Literal

AgentKind = Literal["flights", "hotels", "support", "general"]

SPECIALIST_PROMPTS = {
    "flights": "You are the Flights Specialist. Focus on search, compare, book flights, and payment links.",
    "hotels": "You are the Hotels & Packages Specialist. Focus on stays, resorts, and holiday packages.",
    "support": "You are the Support Specialist. Handle DNC, referrals, price alerts, and account questions.",
    "general": "You are Sarah, TravelAI's lead travel consultant coordinating all services.",
}


def classify_intent(message: str, session: dict) -> AgentKind:
    lower = message.lower()
    hotel_kw = ("hotel", "stay", "resort", "package", "villa", "accommodation", "room")
    support_kw = ("dnc", "unsubscribe", "referral", "complaint", "refund", "cancel booking", "price alert")
    flight_kw = ("flight", "fly", "airport", "dxb", "bom", "ticket", "pnr", "baggage", "visa", "stop")

    if any(k in lower for k in support_kw):
        return "support"
    if any(k in lower for k in hotel_kw):
        return "hotels"
    if any(k in lower for k in flight_kw) or session.get("last_search"):
        return "flights"
    if session.get("origin") and session.get("destination"):
        return "flights"
    return "general"


def specialist_prompt(kind: AgentKind) -> str:
    return SPECIALIST_PROMPTS[kind]
