"""B2C lead miner — buyer intent from Reddit RSS, Telegram groups, Twitter."""

from __future__ import annotations

from typing import Any

from app.services.lead_segment import apply_segment
from app.services.miners.reddit_rss import mine_reddit_rss
from app.services.miners.telegram_groups import mine_telegram_groups, telegram_groups_warning
from app.services.miners.twitter import mine_twitter


async def mine_b2c(cursor: int = 0, batch_size: int = 150) -> tuple[list[dict[str, Any]], int, bool, list[str]]:
    """Aggregate primary B2C buyer-intent sources."""
    warnings: list[str] = []

    rss_leads, rss_stats = await mine_reddit_rss(limit=80)
    telegram_leads, next_cursor, complete, _tg_stats = await mine_telegram_groups(
        cursor=cursor, batch_size=60
    )
    twitter_leads, _tw_stats, tw_warnings = await mine_twitter(limit=40)
    warnings.extend(tw_warnings)

    tw = telegram_groups_warning()
    if tw:
        warnings.append(tw)
    if rss_stats.get("feeds_fetched", 0) == 0:
        warnings.append("Reddit RSS feeds returned no data this run.")

    combined: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in rss_leads + telegram_leads + twitter_leads:
        lead = apply_segment(raw, default="b2c")
        lead.setdefault("lead_category", "consumer")
        key = lead.get("external_id") or lead.get("post_url") or lead.get("phone") or ""
        if not key or key in seen:
            continue
        if not (lead.get("phone") or lead.get("notes") or lead.get("post_url")):
            continue
        seen.add(key)
        combined.append(lead)
        if len(combined) >= batch_size:
            break

    return combined[:batch_size], next_cursor, complete, warnings
