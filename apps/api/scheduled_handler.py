"""Scheduled Lambda worker — hot leads, price alerts, nurture emails, lead miners."""

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger("travel-ai-scheduled")
logger.setLevel(logging.INFO)

MINER_JOBS = {
    "reddit",
    "reddit_rss",
    "telegram",
    "twitter",
    "directories",
    "b2b",
    "b2c",
    "score_leads",
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    job = event.get("job") or event.get("detail", {}).get("job") or os.environ.get("SCRAPER_JOB")
    if job in MINER_JOBS:
        results = asyncio.run(_run_miner_job(job, event))
        return {"statusCode": 200, "body": json.dumps(results)}

    results = asyncio.run(_run_all_jobs())
    return {"statusCode": 200, "body": json.dumps(results)}


async def _run_miner_job(job: str, event: dict[str, Any]) -> dict[str, Any]:
    if job == "score_leads":
        from app.services.lead_scorer import score_unscored_leads

        limit = int(event.get("limit") or 40)
        return await score_unscored_leads(limit=limit)

    if job in {"reddit_rss", "twitter"}:
        from app.services.miners.b2c_import import import_b2c_leads
        from app.services.miners.orchestrator import run_scraper_import

        return await run_scraper_import(job)

    from app.services.miners.orchestrator import run_source_batch

    batch_size = int(event.get("batch_size") or 150)
    cursor = event.get("cursor")
    reset = bool(event.get("reset", False))
    try:
        return await run_source_batch(
            job,
            force=True,
            batch_size=batch_size,
            cursor=cursor,
            reset=reset,
        )
    except Exception as exc:
        logger.exception("Miner %s failed", job)
        return {"source": job, "error": str(exc)}


async def _run_miner(source_id: str, event: dict[str, Any]) -> dict[str, Any]:
    return await _run_miner_job(source_id, event)


async def _run_all_jobs() -> dict[str, Any]:
    from app.services.disruption_monitor import check_disruptions
    from app.services.email_nurture import send_abandoned_search_emails
    from app.services.lead_mining import lead_mining
    from app.services.price_alerts import check_price_alerts
    from app.services.worker_jobs import process_hot_leads

    results: dict[str, Any] = {}
    for name, coro in [
        ("hot_leads", process_hot_leads()),
        ("outbound_mining", lead_mining.process_mined_leads()),
        ("price_alerts", check_price_alerts()),
        ("nurture_emails", send_abandoned_search_emails()),
        ("disruptions", check_disruptions()),
    ]:
        try:
            results[name] = await coro
        except Exception as exc:
            logger.exception("%s failed", name)
            results[name] = {"error": str(exc)}
    return results
