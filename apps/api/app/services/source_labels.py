"""Human-readable labels for lead sources."""

from __future__ import annotations

from typing import Any, Optional

from app.services.miners.travel_parse import parse_travel_text


def _channel_from_detail(source_detail: Optional[str]) -> str | None:
    if not source_detail:
        return None
    if source_detail.startswith("telegram:"):
        return source_detail.split(":", 1)[1].strip()
    return None


def source_display_label(source: Optional[str], source_detail: Optional[str] = None) -> str:
    src = (source or "").lower()
    detail = (source_detail or "").lower()

    if src == "reddit":
        if detail.startswith("r/"):
            return f"Reddit · {source_detail.split('·', 1)[0].strip()}"
        return "Reddit"

    if src == "reddit_rss":
        if detail and detail.startswith("r/"):
            return f"Reddit RSS · {detail}"
        return "Reddit RSS"

    if src == "twitter":
        if detail:
            return f"Twitter · {detail}"
        return "Twitter"

    if src == "telegram":
        if detail and "telegram_group" in detail:
            return f"Telegram Group · {detail.split(':')[-1]}"
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
    """Attach computed display fields; parse notes when route/name missing."""
    out = dict(lead)
    detail = lead.get("source_detail") or (lead.get("enrichment") or {}).get("source_detail")
    out["source_label"] = source_display_label(lead.get("source"), detail)
    out["notes"] = lead.get("notes") or (lead.get("enrichment") or {}).get("notes")

    text = out.get("notes") or ""
    if text:
        channel = _channel_from_detail(detail)
        parsed = parse_travel_text(text, channel=channel)
        for key in (
            "origin", "destination", "departure_date", "return_date",
            "passengers", "budget_max", "location", "name", "travel_intent",
        ):
            if not out.get(key) and parsed.get(key):
                out[key] = parsed[key]

    out["location"] = out.get("location") or (lead.get("enrichment") or {}).get("location")
    out["travel_intent"] = out.get("travel_intent") or lead.get("travel_intent")
    out["route"] = f"{out.get('origin') or '—'} → {out.get('destination') or '—'}"
    if not out.get("name") and text:
        title = parse_travel_text(text, channel=_channel_from_detail(detail)).get("name")
        if title:
            out["name"] = title
    return out
