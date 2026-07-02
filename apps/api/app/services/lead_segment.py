"""B2B vs B2C lead classification."""

from __future__ import annotations

from typing import Any, Optional

from app.services.miners.telegram_intent import stable_digest

B2B_SOURCES = {"directories", "clay", "apollo", "linkedin", "partner"}
B2C_SOURCES = {"reddit", "telegram", "website", "whatsapp", "voice_inbound", "voice_outbound", "google_ads", "meta_ads", "referral", "abandoned_search", "manual"}


def classify_segment(source: Optional[str], explicit: Optional[str] = None) -> str:
    if explicit in {"b2b", "b2c"}:
        return explicit
    src = (source or "").lower()
    if src in B2B_SOURCES:
        return "b2b"
    if src in B2C_SOURCES:
        return "b2c"
    return "b2c"


def apply_segment(raw: dict[str, Any], default: Optional[str] = None) -> dict[str, Any]:
    out = dict(raw)
    out["lead_segment"] = classify_segment(out.get("source"), out.get("lead_segment") or default)
    return out


def segment_display(segment: Optional[str]) -> str:
    if segment == "b2b":
        return "B2B"
    if segment == "b2c":
        return "B2C"
    return "—"


def ensure_contact_phone(raw: dict[str, Any]) -> dict[str, Any]:
    """B2C posts often lack phone — synthesize dedup key from external id."""
    out = dict(raw)
    phone = (out.get("phone") or "").strip()
    if phone:
        return out
    external = out.get("external_id") or out.get("source_detail") or out.get("email")
    if not external:
        return out
    digest = int(stable_digest(str(external), digits=10))
    out["phone"] = f"+888{digest:010d}"[:16]
    out["contact_synthetic"] = True
    return out
