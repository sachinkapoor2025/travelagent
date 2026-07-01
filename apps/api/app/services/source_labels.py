"""Human-readable labels for lead sources."""

from __future__ import annotations

from typing import Any, Optional


def source_display_label(source: Optional[str], source_detail: Optional[str] = None) -> str:
    src = (source or "").lower()
    detail = (source_detail or "").lower()

    if src == "reddit":
        if detail.startswith("r/"):
            return f"Reddit · {source_detail.split('·', 1)[0].strip()}"
        return "Reddit"

    if src == "telegram":
        if detail.startswith("telegram:"):
            channel = source_detail.split(":", 1)[1] if source_detail else "group"
            return f"Telegram · {channel}"
        return "Telegram"

    if src == "directories":
        if detail.startswith("google_maps") or detail.startswith("serpapi") or "google" in detail:
            return "Google Maps"
        if detail.startswith("osm"):
            return "OpenStreetMap"
        return "Google Maps / Directories"

    labels = {
        "clay": "Clay",
        "apollo": "Apollo",
        "linkedin": "LinkedIn",
        "referral": "Referral",
        "website": "Website",
        "whatsapp": "WhatsApp",
        "manual": "Manual",
        "google_ads": "Google Ads",
        "meta_ads": "Meta Ads",
    }
    return labels.get(src, (source or "Unknown").replace("_", " ").title())


def enrich_lead_display(lead: dict[str, Any]) -> dict[str, Any]:
    """Attach computed display fields without mutating stored data."""
    out = dict(lead)
    detail = lead.get("source_detail") or (lead.get("enrichment") or {}).get("source_detail")
    out["source_label"] = source_display_label(lead.get("source"), detail)
    out["location"] = lead.get("location") or (lead.get("enrichment") or {}).get("location")
    out["travel_intent"] = lead.get("travel_intent")
    out["notes"] = lead.get("notes")
    return out
