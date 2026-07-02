"""Telegram GROUP monitor — real people asking for flights (Telethon + public group fallback)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings
from app.services.miners.buyer_intent import (
    extract_phone,
    first_name_only,
    market_from_group,
    passes_buyer_filter,
    stable_lead_id,
)
from app.services.miners.travel_parse import parse_travel_text

settings = get_settings()
logger = logging.getLogger(__name__)

MONITORED_GROUPS = [
    "indiansindubai",
    "dubaiindians",
    "keralites_uae",
    "nri_dubai_group",
    "indians_in_uae",
    "pakistan_uae_community",
    "dubai_expats_community",
    "indians_in_london",
    "uk_desi_community",
    "indians_in_australia",
    "indian_expats_sydney",
    "nri_usa_community",
]

GROUPS_PER_BATCH = 4
MESSAGES_PER_GROUP = 40

_last_warning: str | None = None
_last_stats: dict[str, int] = {}


def telegram_groups_warning() -> str | None:
    return _last_warning


def telegram_groups_stats() -> dict[str, int]:
    return dict(_last_stats)


async def mine_telegram_groups(
    cursor: int = 0,
    batch_size: int = 150,
) -> tuple[list[dict[str, Any]], int, bool, dict[str, int]]:
    """Scan public Telegram groups for buyer-intent messages."""
    global _last_warning, _last_stats
    stats = {"groups_scanned": 0, "messages_checked": 0, "callable": 0, "skipped_deals": 0}
    leads: list[dict[str, Any]] = []

    chunk = MONITORED_GROUPS[cursor : cursor + GROUPS_PER_BATCH]
    next_cursor = cursor + len(chunk)
    complete = next_cursor >= len(MONITORED_GROUPS)

    if settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session_string:
        telethon_leads, tele_stats = await _mine_via_telethon(chunk)
        leads.extend(telethon_leads)
        stats.update(tele_stats)
    else:
        preview_leads, preview_stats = await _mine_via_public_preview(chunk)
        leads.extend(preview_leads)
        stats.update(preview_stats)

    leads = _dedupe(leads)[:batch_size]
    stats["callable"] = len(leads)
    _last_stats = stats

    if not leads:
        if not settings.telegram_api_id:
            _last_warning = (
                "Telegram groups: using public preview mode. For full group access add "
                "TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING to GitHub Secrets."
            )
        elif stats.get("skipped_deals", 0) > 0:
            _last_warning = f"No callable leads — skipped {stats['skipped_deals']} deal/broadcast posts."
        else:
            _last_warning = "No buyer-intent messages in scanned groups this run."
    elif stats.get("skipped_deals", 0) > 0:
        _last_warning = (
            f"Imported {len(leads)} buyer leads; skipped {stats['skipped_deals']} deal posts."
        )
    else:
        _last_warning = None

    return leads, next_cursor, complete, stats


async def _mine_via_telethon(groups: list[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    leads: list[dict[str, Any]] = []
    stats = {"groups_scanned": 0, "messages_checked": 0, "skipped_deals": 0}
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        logger.warning("telethon not installed")
        return [], stats

    client = TelegramClient(
        StringSession(settings.telegram_session_string),
        int(settings.telegram_api_id),
        settings.telegram_api_hash,
    )
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning("Telegram session not authorized")
            return [], stats

        for group in groups:
            try:
                entity = await client.get_entity(group)
                stats["groups_scanned"] += 1
                username = getattr(entity, "username", None) or group
                async for message in client.iter_messages(entity, limit=MESSAGES_PER_GROUP):
                    text = message.message or ""
                    stats["messages_checked"] += 1
                    if not passes_buyer_filter(text):
                        stats["skipped_deals"] += 1
                        continue
                    sender = await message.get_sender()
                    sender_name = first_name_only(
                        getattr(sender, "first_name", None) or getattr(sender, "username", None)
                    )
                    phone = extract_phone(text)
                    msg_id = message.id
                    post_url = f"https://t.me/{username}/{msg_id}"
                    leads.append(_lead_from_message(
                        text,
                        sender_name=sender_name,
                        phone=phone,
                        group_name=username,
                        post_url=post_url,
                        message_id=msg_id,
                        timestamp=message.date.isoformat() if message.date else None,
                    ))
            except Exception:
                logger.exception("Telethon group scan failed for %s", group)
    finally:
        await client.disconnect()

    return leads, stats


async def _mine_via_public_preview(groups: list[str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Fallback: scrape t.me/s/ previews for public supergroups (no Telethon session)."""
    leads: list[dict[str, Any]] = []
    stats = {"groups_scanned": 0, "messages_checked": 0, "skipped_deals": 0}

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        for group in groups:
            try:
                resp = await client.get(f"https://t.me/s/{group.lstrip('@')}")
                if resp.status_code != 200:
                    continue
                stats["groups_scanned"] += 1
                html = resp.text
                blocks = re.findall(
                    r'data-post="([^"]+)"[^>]*>.*?class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                    html,
                    re.DOTALL,
                )
                if not blocks:
                    snippets = re.findall(
                        r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                        html,
                        re.DOTALL,
                    )
                    blocks = [(group, s) for s in snippets[:MESSAGES_PER_GROUP]]

                for post_ref, raw in blocks[:MESSAGES_PER_GROUP]:
                    text = re.sub(r"<[^>]+>", " ", raw).strip()
                    text = re.sub(r"\s+", " ", text)
                    stats["messages_checked"] += 1
                    if not passes_buyer_filter(text):
                        stats["skipped_deals"] += 1
                        continue
                    if "/" in post_ref:
                        post_url = f"https://t.me/{post_ref}"
                        msg_id = post_ref.split("/")[-1]
                    else:
                        msg_id = stable_lead_id("tg", text)[:8]
                        post_url = f"https://t.me/{group.lstrip('@')}"
                    phone = extract_phone(text)
                    leads.append(_lead_from_message(
                        text,
                        sender_name="—",
                        phone=phone,
                        group_name=group.lstrip("@"),
                        post_url=post_url,
                        message_id=msg_id,
                    ))
            except Exception:
                logger.exception("Telegram group preview failed for %s", group)

    return leads, stats


def _lead_from_message(
    text: str,
    *,
    sender_name: str,
    phone: str,
    group_name: str,
    post_url: str,
    message_id: str | int,
    timestamp: str | None = None,
) -> dict[str, Any]:
    parsed = parse_travel_text(text, channel=group_name)
    market = market_from_group(group_name)
    external_id = stable_lead_id("telegram", f"{group_name}:{message_id}")
    lead: dict[str, Any] = {
        "name": sender_name if sender_name != "—" else parsed.get("name"),
        "phone": phone,
        "source": "telegram",
        "source_detail": f"telegram_group:@{group_name}",
        "external_id": external_id,
        "lead_segment": "b2c",
        "lead_category": "consumer",
        "call_ready": True,
        "post_url": post_url,
        "contact_url": post_url,
        "market": market,
        "notes": text[:300].strip(),
        "opt_in_marketing": True,
        "scored": False,
        "status": "new",
        "preferred_language": "hi" if market in {"uae", "india"} else "en",
    }
    if timestamp:
        lead["message_at"] = timestamp
    for key in ("origin", "destination", "departure_date", "return_date", "passengers", "budget_max", "location"):
        if parsed.get(key):
            lead[key] = parsed[key]
    return lead


def _dedupe(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for lead in leads:
        key = lead.get("external_id") or lead.get("post_url") or ""
        if key and key not in seen:
            seen.add(key)
            out.append(lead)
    return out
