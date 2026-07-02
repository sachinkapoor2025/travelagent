"""B2C lead miner — consumers seeking travel (Reddit + Telegram + SerpAPI)."""

from __future__ import annotations

from typing import Any

from app.services.lead_segment import apply_segment
from app.services.miners.reddit import mine_reddit, reddit_setup_warning
from app.services.miners.serp_b2c import mine_serp_b2c
from app.services.miners.telegram import mine_telegram_legacy, telegram_setup_warning


async def mine_b2c(cursor: int = 0, batch_size: int = 150) -> tuple[list[dict[str, Any]], int, bool, list[str]]:
    """Aggregate B2C sources. Cursor tracks Reddit subreddit offset."""
    warnings: list[str] = []
    reddit_leads, next_cursor, reddit_done = await mine_reddit(
        limit_per_sub=25,
        subreddit_offset=cursor,
        max_subreddits=8,
    )
    telegram_leads = await mine_telegram_legacy()
    serp_leads = await mine_serp_b2c(limit=40)

    rw = reddit_setup_warning()
    tw = telegram_setup_warning()
    if rw:
        warnings.append(rw)
    if tw:
        warnings.append(tw)
    if not serp_leads and not reddit_leads:
        from app.config import get_settings

        if not get_settings().serpapi_key:
            warnings.append(
                "Optional: add SERPAPI_KEY for Google travel-intent B2C leads without Reddit."
            )

    combined: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in serp_leads + reddit_leads + telegram_leads:
        lead = apply_segment(raw, default="b2c")
        key = lead.get("external_id") or lead.get("source_detail") or lead.get("phone") or ""
        if not key or key in seen:
            continue
        if not (lead.get("phone") or lead.get("destination") or lead.get("notes") or lead.get("email")):
            continue
        seen.add(key)
        combined.append(lead)
        if len(combined) >= batch_size:
            break

    complete = reddit_done and len(combined) < batch_size
    return combined[:batch_size], next_cursor, complete, warnings
