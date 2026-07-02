"""Telegram B2C miner — bot updates + public channel previews with rich parsing."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings
from app.services.miners.travel_parse import parse_travel_text

settings = get_settings()
logger = logging.getLogger(__name__)

TRAVEL_KW = re.compile(
    r"\b(flight|ticket|visa|hotel|package|travel|trip|dubai|delhi|mumbai|melbourne|london|paris|tokyo|bali|booking|need|looking|deal|fare|airfare)\b",
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
    """Mine from bot updates and public channel previews."""
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
            channel = chat.get("username") or chat.get("title") or "chat"
            display_name = from_user.get("first_name") or from_user.get("username")
            leads.append(_lead_from_text(
                text,
                name=display_name,
                phone=phone_match.group(1) if phone_match else "",
                channel=channel if not display_name else None,
                source_detail=f"telegram:{chat.get('title') or channel}",
                external_id=f"telegram:{msg.get('message_id', update.get('update_id'))}",
            ))
    return leads


async def _mine_via_public_preview() -> list[dict[str, Any]]:
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
                    snippets = re.findall(r'dir="auto"[^>]*>([^<]{20,800})', html)
                for raw in snippets[:15]:
                    text = re.sub(r"<[^>]+>", " ", raw).strip()
                    text = re.sub(r"\s+", " ", text)
                    if len(text) < 15 or not TRAVEL_KW.search(text):
                        continue
                    phone_match = PHONE_RE.search(text)
                    leads.append(_lead_from_text(
                        text,
                        phone=phone_match.group(1) if phone_match else "",
                        channel=channel.lstrip("@"),
                        source_detail=f"telegram:@{channel.lstrip('@')}",
                        external_id=f"telegram:{channel}:{hash(text) % 10**12}",
                    ))
            except Exception:
                logger.exception("Telegram preview failed for %s", channel)
    return leads


def _lead_from_text(
    text: str,
    *,
    name: str | None = None,
    phone: str = "",
    channel: str | None = None,
    source_detail: str = "telegram",
    external_id: str = "",
) -> dict[str, Any]:
    parsed = parse_travel_text(text, channel=channel)
    lead: dict[str, Any] = {
        "phone": phone,
        "source": "telegram",
        "source_detail": source_detail,
        "external_id": external_id or f"telegram:{hash(text) % 10**10}",
        "lead_segment": "b2c",
        "notes": text[:800].strip(),
        "opt_in_marketing": True,
    }
    for key in ("origin", "destination", "departure_date", "return_date", "passengers", "budget_max", "location", "travel_intent"):
        if parsed.get(key):
            lead[key] = parsed[key]
    if name:
        lead["name"] = name
    elif parsed.get("name"):
        lead["name"] = parsed["name"]
    if not lead.get("destination"):
        lead["destination"] = parsed.get("destination")
    return lead


def _dedupe(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for lead in leads:
        key = lead.get("external_id") or lead.get("notes") or lead.get("phone") or ""
        if key and key not in seen:
            seen.add(key)
            out.append(lead)
    return out
