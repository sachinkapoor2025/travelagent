"""Telegram B2C miner — real user messages (bot), not promotional deal channels."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings
from app.services.miners.telegram_intent import classify_telegram_lead, stable_digest
from app.services.miners.travel_parse import parse_travel_text

settings = get_settings()
logger = logging.getLogger(__name__)

TRAVEL_KW = re.compile(
    r"\b(flight|ticket|visa|hotel|package|travel|trip|dubai|delhi|mumbai|melbourne|"
    r"london|paris|tokyo|bali|booking|need|looking|fare|airfare)\b",
    re.I,
)
PHONE_RE = re.compile(r"(\+?\d{10,14})")

# Public deal/broadcast channels — not callable customers. Use TELEGRAM_CHANNELS for
# groups where travelers ask questions (bot must be a member).
REQUEST_GROUP_HINTS = [
    "travelhelp", "flighthelp", "visadubai", "indiatouae", "expatsdubai",
]

CHANNELS_PER_BATCH = 4
POSTS_PER_CHANNEL = 20

_last_warning: str | None = None
_last_stats: dict[str, int] = {}


def telegram_setup_warning() -> str | None:
    return _last_warning


def telegram_last_stats() -> dict[str, int]:
    return dict(_last_stats)


def _channel_list() -> list[str]:
    extra = [c.strip().lstrip("@") for c in (settings.telegram_channels or "").split(",") if c.strip()]
    combined = extra + REQUEST_GROUP_HINTS
    seen: set[str] = set()
    out: list[str] = []
    for ch in combined:
        key = ch.lower()
        if key not in seen:
            seen.add(key)
            out.append(ch)
    return out


async def mine_telegram(
    cursor: int = 0,
    batch_size: int = 150,
) -> tuple[list[dict[str, Any]], int, bool, dict[str, int]]:
    """Mine callable consumer leads from bot updates (+ optional request groups)."""
    global _last_warning, _last_stats
    leads: list[dict[str, Any]] = []
    stats = {"bot_messages": 0, "callable": 0, "skipped_deals": 0, "channels_scanned": 0}

    if settings.telegram_bot_token:
        bot_leads, bot_stats = await _mine_via_bot()
        stats.update(bot_stats)
        leads.extend(bot_leads)

    channels = _channel_list()
    if channels:
        preview_leads, preview_stats, next_cursor = await _mine_via_public_preview(
            channels, cursor=cursor, channels_per_batch=CHANNELS_PER_BATCH
        )
        for key, val in preview_stats.items():
            stats[key] = stats.get(key, 0) + val
        leads.extend(preview_leads)
        complete = next_cursor >= len(channels)
    else:
        next_cursor = 0
        complete = True

    leads = _dedupe(leads)[:batch_size]
    stats["callable"] = len(leads)
    _last_stats = stats

    if not leads:
        if not settings.telegram_bot_token:
            _last_warning = (
                "Add TELEGRAM_BOT_TOKEN to GitHub Secrets and redeploy. "
                "Add your bot to travel help groups where people ask for flights."
            )
        elif stats.get("skipped_deals", 0) > 0:
            _last_warning = (
                f"Skipped {stats['skipped_deals']} promotional deal posts (not callable customers). "
                "Add bot to travel request groups or use Reddit B2C for people looking for flights."
            )
        elif stats.get("bot_messages", 0) == 0:
            _last_warning = (
                "No traveler messages yet. Add bot to groups like 'Need flight Mumbai to Dubai' "
                "or DM the bot. Deal channels are ignored — they are not callable leads."
            )
        else:
            _last_warning = None
    elif stats.get("skipped_deals", 0) > 0:
        _last_warning = (
            f"Imported {len(leads)} callable leads; skipped {stats['skipped_deals']} deal/broadcast posts."
        )
    else:
        _last_warning = None

    return leads, next_cursor, complete, stats


async def mine_telegram_legacy() -> list[dict[str, Any]]:
    """Backward-compatible wrapper used by b2c bundle miner."""
    leads, _, _, _ = await mine_telegram(cursor=0, batch_size=150)
    return leads


async def _mine_via_bot() -> tuple[list[dict[str, Any]], dict[str, int]]:
    leads: list[dict[str, Any]] = []
    stats = {"bot_messages": 0, "skipped_deals": 0}
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
            params={"limit": 100, "allowed_updates": '["message","channel_post","edited_message"]'},
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("Telegram getUpdates failed: %s", data)
            return [], stats
        for update in data.get("result", []):
            msg = update.get("message") or update.get("channel_post") or update.get("edited_message") or {}
            text = msg.get("text") or msg.get("caption") or ""
            if not text or not TRAVEL_KW.search(text):
                continue
            stats["bot_messages"] += 1
            phone_match = PHONE_RE.search(text)
            has_phone = bool(phone_match)
            from_user = msg.get("from") or {}
            chat = msg.get("chat") or {}
            is_channel = msg.get("channel_post") is not None or chat.get("type") == "channel"
            call_ready, _reason = classify_telegram_lead(
                text,
                from_bot_user=bool(from_user.get("id")),
                has_real_phone=has_phone,
                is_channel_preview=is_channel,
            )
            if not call_ready:
                stats["skipped_deals"] += 1
                continue
            channel = chat.get("username") or chat.get("title") or "chat"
            display_name = from_user.get("first_name") or from_user.get("username")
            msg_id = msg.get("message_id", update.get("update_id"))
            leads.append(_lead_from_text(
                text,
                name=display_name,
                phone=phone_match.group(1) if phone_match else "",
                channel=channel if not display_name else None,
                source_detail=f"telegram:{chat.get('title') or channel}",
                external_id=f"telegram:bot:{chat.get('id')}:{msg_id}",
                call_ready=True,
            ))
    return leads, stats


async def _mine_via_public_preview(
    channels: list[str],
    *,
    cursor: int,
    channels_per_batch: int,
) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    leads: list[dict[str, Any]] = []
    stats = {"channels_scanned": 0, "skipped_deals": 0}
    chunk = channels[cursor : cursor + channels_per_batch]
    next_cursor = cursor + len(chunk)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for channel in chunk:
            try:
                resp = await client.get(f"https://t.me/s/{channel.lstrip('@')}")
                if resp.status_code != 200:
                    continue
                stats["channels_scanned"] += 1
                html = resp.text
                snippets = re.findall(
                    r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                    html,
                    re.DOTALL,
                )
                if not snippets:
                    snippets = re.findall(r'dir="auto"[^>]*>([^<]{20,800})', html)
                for raw in snippets[:POSTS_PER_CHANNEL]:
                    text = re.sub(r"<[^>]+>", " ", raw).strip()
                    text = re.sub(r"\s+", " ", text)
                    if len(text) < 15 or not TRAVEL_KW.search(text):
                        continue
                    phone_match = PHONE_RE.search(text)
                    call_ready, _reason = classify_telegram_lead(
                        text,
                        has_real_phone=bool(phone_match),
                        is_channel_preview=True,
                    )
                    if not call_ready:
                        stats["skipped_deals"] += 1
                        continue
                    ch = channel.lstrip("@")
                    text_key = stable_digest(text, digits=16)
                    leads.append(_lead_from_text(
                        text,
                        phone=phone_match.group(1) if phone_match else "",
                        channel=ch,
                        source_detail=f"telegram:@{ch}",
                        external_id=f"telegram:{ch}:{text_key}",
                        call_ready=True,
                    ))
            except Exception:
                logger.exception("Telegram preview failed for %s", channel)
    return leads, stats, next_cursor


def _lead_from_text(
    text: str,
    *,
    name: str | None = None,
    phone: str = "",
    channel: str | None = None,
    source_detail: str = "telegram",
    external_id: str = "",
    call_ready: bool = True,
) -> dict[str, Any]:
    parsed = parse_travel_text(text, channel=channel)
    lead: dict[str, Any] = {
        "phone": phone,
        "source": "telegram",
        "source_detail": source_detail,
        "external_id": external_id or f"telegram:{stable_digest(text, digits=16)}",
        "lead_segment": "b2c",
        "call_ready": call_ready,
        "notes": text[:800].strip(),
        "opt_in_marketing": True,
    }
    for key in (
        "origin", "destination", "departure_date", "return_date",
        "passengers", "budget_max", "location", "travel_intent",
    ):
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
