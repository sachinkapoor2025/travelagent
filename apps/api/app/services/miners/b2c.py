"""B2C lead miner — consumers seeking travel (Reddit + Telegram + forums)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.lead_segment import apply_segment
from app.services.miners.reddit import mine_reddit
from app.services.miners.telegram import mine_telegram


async def mine_b2c(cursor: int = 0, batch_size: int = 150) -> tuple[list[dict[str, Any]], int, bool]:
    """Aggregate B2C sources. Cursor tracks Reddit subreddit offset."""
    reddit_leads, next_cursor, reddit_done = await mine_reddit(
        limit_per_sub=25,
        subreddit_offset=cursor,
        max_subreddits=8,
    )
    telegram_leads = await mine_telegram()

    combined: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in reddit_leads + telegram_leads:
        lead = apply_segment(raw, default="b2c")
        key = lead.get("phone") or lead.get("source_detail") or lead.get("name") or ""
        if not key or key in seen:
            continue
        if not lead.get("phone") and not lead.get("destination") and not lead.get("notes"):
            continue
        seen.add(key)
        combined.append(lead)
        if len(combined) >= batch_size:
            break

    complete = reddit_done and len(combined) < batch_size
    return combined[:batch_size], next_cursor, complete
