"""Traveler preference memory — persisted on lead records by phone."""

from typing import Any, Optional

from app.storage.leads_repo import lead_repo


PREF_FIELDS = (
    "preferred_language",
    "origin",
    "destination",
    "cabin_class",
    "stop_preference",
    "passengers",
    "budget_max",
    "home_airport",
)


async def load_preferences(phone: Optional[str]) -> dict[str, Any]:
    if not phone:
        return {}
    leads = await lead_repo.list_by_phone(phone)
    if not leads:
        return {}
    lead = leads[0]
    prefs = {k: lead.get(k) for k in PREF_FIELDS if lead.get(k) is not None}
    if lead.get("market"):
        prefs["market"] = lead["market"]
    return prefs


async def save_preferences(phone: str, updates: dict[str, Any]) -> dict[str, Any]:
    data = {"phone": phone}
    for key in PREF_FIELDS:
        if key in updates and updates[key] is not None:
            data[key] = updates[key]
    if updates.get("market"):
        data["market"] = updates["market"]
    lead = await lead_repo.create_or_update(data)
    return {k: lead.get(k) for k in PREF_FIELDS if lead.get(k) is not None}


def format_prefs_for_prompt(prefs: dict[str, Any]) -> str:
    if not prefs:
        return ""
    parts = [f"{k}={v}" for k, v in prefs.items()]
    return "Known traveler preferences: " + ", ".join(parts) + ". Use these as defaults unless the customer says otherwise."
