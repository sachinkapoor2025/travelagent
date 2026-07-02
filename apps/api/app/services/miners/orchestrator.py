"""Orchestrate all lead mining sources with batched global fetch."""

from __future__ import annotations

import logging
from typing import Any

from app.services.lead_enrichment import lead_enrichment
from app.services.lead_mining import lead_mining
from app.services.lead_segment import apply_segment, ensure_contact_phone
from app.services.miners.b2c_import import import_b2c_leads
from app.services.mining_config import get_sources, record_run
from app.services.mining_progress import (
    DEFAULT_BATCH_SIZE,
    get_progress,
    reset_progress,
    save_progress,
)
from app.services.miners.b2b import mine_b2b
from app.services.miners.b2c import mine_b2c
from app.services.miners.directories import mine_directories_batch
from app.services.miners.global_markets import GLOBAL_MARKETS
from app.services.miners.reddit import mine_reddit
from app.services.miners.reddit_rss import mine_reddit_rss
from app.services.miners.telegram_groups import mine_telegram_groups
from app.services.miners.twitter import mine_twitter

logger = logging.getLogger(__name__)

MINERS = {
    "reddit": mine_reddit,
    "directories": None,
    "b2b": mine_b2b,
    "b2c": mine_b2c,
}

SEGMENT_FOR_SOURCE = {
    "directories": "b2b",
    "b2b": "b2b",
    "reddit": "b2c",
    "reddit_rss": "b2c",
    "telegram": "b2c",
    "twitter": "b2c",
    "b2c": "b2c",
}


def _telegram_group_count() -> int:
    from app.services.miners.telegram_groups import MONITORED_GROUPS

    return len(MONITORED_GROUPS)


async def run_scraper_import(source_id: str) -> dict[str, Any]:
    """Run standalone B2C scrapers (reddit_rss, twitter) and record stats."""
    from app.storage.dynamo import now_iso

    warnings: list[str] = []
    if source_id == "reddit_rss":
        raw, stats = await mine_reddit_rss(limit=200)
        if stats.get("feeds_fetched", 0) == 0:
            warnings.append("Reddit RSS returned no feeds — check network or Reddit availability.")
    elif source_id == "twitter":
        raw, stats, tw_warnings = await mine_twitter(limit=200)
        warnings.extend(tw_warnings)
    else:
        return {"error": f"Unknown scraper {source_id}"}

    result = await import_b2c_leads(raw, source_id=source_id)
    ts = now_iso()
    message = f"{source_id}: imported {result['imported']} buyer-intent leads"
    if warnings:
        message += f" · {warnings[0]}"

    stats_out = {
        "source": source_id,
        **result,
        "message": message,
        "last_run_at": ts,
        "warnings": warnings,
    }
    try:
        record_run(source_id, stats_out)
    except Exception:
        logger.exception("Failed to record run for %s", source_id)
    return stats_out


async def run_source_batch(
    source_id: str,
    force: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    cursor: int | None = None,
    reset: bool = False,
) -> dict[str, Any]:
    """Import up to batch_size leads, advance cursor, track progress."""
    sources = get_sources()
    if source_id in {"clay", "apollo"}:
        return {
            "source": source_id,
            "skipped": True,
            "reason": "Webhook-only source — configure Clay/Apollo to POST to /lead-mining/webhook/" + source_id,
        }
    known = set(MINERS) | {"directories", "telegram", "reddit_rss", "twitter"}
    if source_id not in known:
        return {"error": f"Unknown source {source_id}"}
    if not force and not sources.get(source_id, {}).get("enabled", False):
        return {"skipped": True, "reason": "disabled"}

    if reset:
        reset_progress(source_id, segment=SEGMENT_FOR_SOURCE.get(source_id))

    progress = get_progress(source_id)
    start_cursor = cursor if cursor is not None else int(progress.get("cursor") or 0)
    segment = SEGMENT_FOR_SOURCE.get(source_id, "b2c")
    warnings: list[str] = []

    try:
        raw_leads, next_cursor, complete, total_markets, warnings = await _fetch_batch(
            source_id, start_cursor, batch_size
        )
    except Exception as exc:
        logger.exception("Miner fetch failed for %s", source_id)
        return {"source": source_id, "error": str(exc), "imported": 0, "raw_found": 0}

    if source_id in {"telegram", "reddit_rss", "twitter"}:
        import_result = await import_b2c_leads(raw_leads, source_id=source_id)
        imported = import_result["imported"]
        errors = import_result.get("errors", 0)
    else:
        imported = 0
        errors = 0
        for raw in raw_leads:
            lead = apply_segment(raw, default=segment)
            if source_id == "directories":
                lead["lead_category"] = "b2b"
                lead["lead_segment"] = "b2b"
            lead = ensure_contact_phone(lead)
            if lead.get("call_ready") is False or lead.get("lead_category") == "deal_channel":
                continue
            if not (
                lead.get("phone")
                or lead.get("destination")
                or lead.get("notes")
                or lead.get("email")
            ):
                continue
            try:
                enriched = await lead_enrichment.enrich_fast(lead)
                enriched["scored"] = True
                await lead_mining._save_lead(enriched)  # noqa: SLF001
                imported += 1
            except Exception:
                logger.exception("Failed to import mined lead from %s", source_id)
                errors += 1

    total_imported = int(progress.get("total_imported") or 0) + imported
    from app.storage.dynamo import now_iso

    ts = now_iso()
    if complete and total_imported == 0 and segment == "b2c":
        hint = "; ".join(warnings[:2]) if warnings else "Add Telegram session or wait for buyer posts in monitored groups."
        message = f"No B2C leads found in this run. {hint}"
    elif complete:
        message = f"All leads fetched — {total_imported} total imported · completed {ts}"
    elif imported == 0 and warnings:
        message = f"No new leads this batch. {warnings[0]}"
    else:
        remaining = max((total_markets or len(GLOBAL_MARKETS)) - next_cursor, 0)
        message = f"Batch done — {imported} imported ({total_imported} total). ~{remaining} remaining — fetch next batch."

    state = save_progress(
        source_id,
        cursor=next_cursor if not complete else next_cursor,
        total_markets=total_markets or len(GLOBAL_MARKETS),
        total_imported=total_imported,
        last_batch_imported=imported,
        last_run_at=ts,
        complete=complete,
        completed_at=ts if complete else progress.get("completed_at"),
        segment=segment,
        message=message,
        raw_found_last=len(raw_leads),
        has_more=not complete,
        markets_remaining=max(int(total_markets or len(GLOBAL_MARKETS)) - int(next_cursor), 0),
    )

    stats = {
        "imported": imported,
        "raw_found": len(raw_leads),
        "errors": errors,
        "cursor": state["cursor"],
        "next_cursor": state["cursor"],
        "complete": complete,
        "total_imported": total_imported,
        "total_markets": state.get("total_markets"),
        "markets_remaining": max(int(state.get("total_markets") or 0) - int(state["cursor"]), 0),
        "message": message,
        "last_run_at": ts,
        "completed_at": state.get("completed_at"),
        "segment": segment,
        "has_more": not complete,
        "warnings": warnings,
    }
    try:
        record_run(source_id, stats)
    except Exception:
        logger.exception("Failed to record mining run for %s", source_id)

    return {"source": source_id, **stats}


async def _fetch_batch(
    source_id: str,
    cursor: int,
    batch_size: int,
) -> tuple[list[dict[str, Any]], int, bool, int, list[str]]:
    if source_id == "b2b":
        leads, next_cursor, complete, total = await mine_b2b(cursor=cursor, batch_size=batch_size)
        return leads, next_cursor, complete, total, []
    if source_id == "b2c":
        leads, next_cursor, complete, warnings = await mine_b2c(cursor=cursor, batch_size=batch_size)
        return leads, next_cursor, complete, 0, warnings
    if source_id == "directories":
        leads, next_cursor, complete, total = await mine_directories_batch(cursor=cursor, import_limit=batch_size)
        tagged = []
        for lead in leads:
            item = apply_segment(lead, default="b2b")
            item["lead_category"] = "b2b"
            item["lead_segment"] = "b2b"
            tagged.append(item)
        return tagged, next_cursor, complete, total, []
    if source_id == "reddit":
        from app.services.miners.reddit import reddit_setup_warning

        leads, next_cursor, complete = await mine_reddit(limit_per_sub=25, subreddit_offset=cursor, max_subreddits=10)
        w = [x for x in [reddit_setup_warning()] if x]
        return [apply_segment(l, default="b2c") for l in leads[:batch_size]], next_cursor, complete, 0, w
    if source_id == "reddit_rss":
        raw, stats = await mine_reddit_rss(limit=batch_size)
        w = []
        if stats.get("feeds_fetched", 0) == 0:
            w.append("Reddit RSS feeds unavailable.")
        return raw[:batch_size], 0, True, 0, w
    if source_id == "twitter":
        raw, _stats, w = await mine_twitter(limit=batch_size)
        return raw[:batch_size], 0, True, 0, w
    if source_id == "telegram":
        from app.services.miners.telegram_groups import (
            mine_telegram_groups,
            telegram_groups_warning,
        )

        raw, next_cursor, complete, tg_stats = await mine_telegram_groups(cursor=cursor, batch_size=batch_size)
        skipped = tg_stats.get("skipped_deals", 0)
        w = [x for x in [telegram_groups_warning()] if x]
        if skipped and not w:
            w = [f"Skipped {skipped} promotional posts."]
        tagged = [apply_segment(l, default="b2c") for l in raw[:batch_size]]
        return tagged, next_cursor, complete, _telegram_group_count(), w
    return [], cursor, True, 0, []


async def run_source(source_id: str, force: bool = False, fast: bool = False) -> dict[str, Any]:
    """Legacy single-run wrapper — one batch."""
    return await run_source_batch(source_id, force=force, batch_size=DEFAULT_BATCH_SIZE, reset=False)


async def run_all_enabled() -> dict[str, Any]:
    results = {}
    for source_id in ("b2b", "b2c", "reddit_rss", "telegram", "twitter", "directories"):
        try:
            if source_id in {"reddit_rss", "twitter"}:
                results[source_id] = await run_scraper_import(source_id)
            else:
                results[source_id] = await run_source_batch(source_id, force=True, batch_size=100)
        except Exception as exc:
            logger.exception("Miner %s failed", source_id)
            results[source_id] = {"error": str(exc)}
    return results
