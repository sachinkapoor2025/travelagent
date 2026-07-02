"""Telegram B2C miner — bot updates + optional public channel list."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

TRAVEL_KW = re.compile(
    r"\b(flight|ticket|visa|hotel|package|travel|trip|dubai|delhi|mumbai|melbourne|london|paris|tokyo|bali|booking|need|looking)\b",
    re.I,
)
PHONE_RE = re.compile(r"(\+?\d{10,14})")

DEFAULT_CHANNELS = [
    "traveldeals", "TravelHacks", "dubaitravel", "uaetravelers", "indiatravel",
    "solotravel", "backpacking", "visa_information", "flightdeals",
]

_last_warning: str | None = None


def telegram_setup_warning() -> str | None:
    return _last_warning


def _channel_list() -> list[str]:
    extra = [c.strip().lstrip("@") for c in (settings.telegram_channels or "").split(",") if c.strip()]
    combined = extra + DEFAULT_CHANNELS
    seen: set[str] = set()
    out: list[str] = []
    for ch in combined:
        if ch.lower() not in seen:
            seen.add(ch.lower())
            out.append(ch)
    return out


async def mine_telegram() -> list[dict[str, Any]]:
    """Mine from bot updates and any configured public channel previews."""
    global _last_warning
    leads: list[dict[str, Any]] = []
    bot_count = 0

    if settings.telegram_bot_token:
        bot_leads = await _mine_via_bot()
        bot_count = len(bot_leads)
        leads.extend(bot_leads)

    preview_leads = await _mine_via_public_preview()
    leads.extend(preview_leads)

    leads = _dedupe(leads)
    if not leads:
        if not settings.telegram_bot_token:
            _last_warning = "Add TELEGRAM_BOT_TOKEN to GitHub Secrets and redeploy."
        elif bot_count == 0:
            _last_warning = (
                "Bot has no messages yet. Add bot to travel groups as member, make it admin on "
                "your channel, or DM it: 'Need flight Mumbai to Dubai July'."
            )
        else:
            _last_warning = None
    else:
        _last_warning = None
    return leads


async def _mine_via_bot() -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
            params={"limit": 100, "allowed_updates": '["message","channel_post","edited_message"]'},
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("Telegram getUpdates failed: %s", data)
            return []
        for update in data.get("result", []):
            msg = update.get("message") or update.get("channel_post") or update.get("edited_message") or {}
            text = msg.get("text") or msg.get("caption") or ""
            if not text or not TRAVEL_KW.search(text):
                continue
            phone_match = PHONE_RE.search(text)
            from_user = msg.get("from") or {}
            chat = msg.get("chat") or {}
            leads.append(_lead_from_text(
                text,
                name=from_user.get("first_name") or from_user.get("username"),
                phone=phone_match.group(1) if phone_match else "",
                source_detail=f"telegram:{chat.get('title') or chat.get('username') or 'chat'}",
                external_id=f"telegram:{msg.get('message_id', update.get('update_id'))}",
            ))
    return leads


async def _mine_via_public_preview() -> list[dict[str, Any]]:
    """Best-effort scrape of t.me/s previews (may return empty if Telegram changes HTML)."""
    leads: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for channel in _channel_list()[:12]:
            try:
                resp = await client.get(f"https://t.me/s/{channel.lstrip('@')}")
                if resp.status_code != 200:
                    continue
                html = resp.text
                snippets = re.findall(
                    r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                    html,
                    re.DOTALL,
                )
                if not snippets:
                    snippets = re.findall(r'dir="auto"[^>]*>([^<]{20,500})', html)
                for raw in snippets[:15]:
                    text = re.sub(r"<[^>]+>", " ", raw).strip()
                    text = re.sub(r"\s+", " ", text)
                    if len(text) < 15 or not TRAVEL_KW.search(text):
                        continue
                    phone_match = PHONE_RE.search(text)
                    leads.append(_lead_from_text(
                        text,
                        phone=phone_match.group(1) if phone_match else "",
                        source_detail=f"telegram:@{channel.lstrip('@')}",
                        external_id=f"telegram:{channel}:{text[:50]}",
                    ))
            except Exception:
                logger.exception("Telegram preview failed for %s", channel)
    return leads


def _lead_from_text(
    text: str,
    *,
    name: str | None = None,
    phone: str = "",
    source_detail: str = "telegram",
    external_id: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "phone": phone,
        "destination": _extract_destination(text),
        "market": _market_from_text(text),
        "source": "telegram",
        "source_detail": source_detail,
        "external_id": external_id or f"telegram:{hash(text) % 10**10}",
        "lead_segment": "b2c",
        "travel_intent": "researching",
        "notes": text[:500].strip(),
        "opt_in_marketing": True,
    }


def _dedupe(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for lead in leads:
        key = lead.get("external_id") or lead.get("notes") or lead.get("phone") or ""
        if key and key not in seen:
            seen.add(key)
            out.append(lead)
    return out


def _market_from_text(text: str) -> str:
    lower = text.lower()
    if any(x in lower for x in ("dubai", "uae", "abu dhabi")):
        return "uae"
    if any(x in lower for x in ("india", "delhi", "mumbai")):
        return "india"
    if any(x in lower for x in ("london", " uk ", "britain")):
        return "uk"
    if any(x in lower for x in ("australia", "melbourne", "sydney")):
        return "au"
    return "global"


def _extract_destination(text: str) -> str | None:
    lower = text.lower()
    for name, code in {
        "dubai": "DXB", "delhi": "DEL", "mumbai": "BOM", "melbourne": "MEL",
        "london": "LHR", "paris": "CDG", "tokyo": "NRT", "bali": "DPS",
        "bangkok": "BKK", "singapore": "SIN",
    }.items():
        if name in lower:
            return code
    return None
