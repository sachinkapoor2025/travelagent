"""Telegram lead miner — public travel group keywords via Bot API or configured channels."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import get_settings

settings = get_settings()

TRAVEL_KW = re.compile(r"\b(flight|ticket|visa|hotel|package|travel|trip|dubai|delhi|melbourne)\b", re.I)
PHONE_RE = re.compile(r"(\+?\d{10,14})")

# Public channel usernames to monitor (travel/expat groups)
DEFAULT_CHANNELS = [
    "@dubaitravel", "@uaetravelers", "@indiatravel", "@traveldeals",
]


async def mine_telegram() -> list[dict[str, Any]]:
    """Mine leads from configured Telegram bot updates or channel scrape fallback."""
    if settings.telegram_bot_token:
        return await _mine_via_bot()
    return await _mine_via_public_preview()


async def _mine_via_bot() -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
            params={"limit": 100},
        )
        if resp.status_code != 200:
            return []
        for update in resp.json().get("result", []):
            msg = update.get("message") or update.get("channel_post") or {}
            text = msg.get("text") or msg.get("caption") or ""
            if not TRAVEL_KW.search(text):
                continue
            phone_match = PHONE_RE.search(text)
            from_user = msg.get("from") or {}
            leads.append(
                {
                    "name": from_user.get("first_name") or from_user.get("username"),
                    "phone": phone_match.group(1) if phone_match else "",
                    "destination": _extract_destination(text),
                    "market": "uae",
                    "source": "telegram",
                    "source_detail": f"telegram:{msg.get('chat', {}).get('title', 'group')}",
                    "opt_in_marketing": True,
                }
            )
    return [l for l in leads if l.get("phone") or l.get("destination")]


async def _mine_via_public_preview() -> list[dict[str, Any]]:
    """Lightweight fallback when no bot token — returns structured placeholders for demo."""
    leads: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for channel in DEFAULT_CHANNELS:
            try:
                resp = await client.get(f"https://t.me/s/{channel.lstrip('@')}")
                if resp.status_code != 200:
                    continue
                snippets = re.findall(r'class="tgme_widget_message_text[^"]*"[^>]*>([^<]+)', resp.text)
                for snippet in snippets[:10]:
                    text = re.sub(r"<[^>]+>", " ", snippet)
                    if not TRAVEL_KW.search(text):
                        continue
                    phone_match = PHONE_RE.search(text)
                    leads.append(
                        {
                            "name": None,
                            "phone": phone_match.group(1) if phone_match else "",
                            "destination": _extract_destination(text),
                            "market": "uae" if "dubai" in channel.lower() or "uae" in channel.lower() else "india",
                            "source": "telegram",
                            "source_detail": channel,
                            "opt_in_marketing": True,
                        }
                    )
            except Exception:
                continue
    return [l for l in leads if l.get("destination")]


def _extract_destination(text: str) -> str | None:
    lower = text.lower()
    for name, code in {"dubai": "DXB", "delhi": "DEL", "melbourne": "MEL", "london": "LHR"}.items():
        if name in lower:
            return code
    return None
