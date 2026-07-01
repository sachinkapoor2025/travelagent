"""Scheduled Lambda worker — hot leads, price alerts, nurture emails, lead miners."""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("travel-ai-scheduled")
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    job = event.get("job") or event.get("detail", {}).get("job")
    miner_jobs = {"reddit", "telegram", "directories", "b2b", "b2c"}
    if job in miner_jobs:
        results = asyncio.run(_run_miner(job, event))
        return {"statusCode": 200, "body": json.dumps(results)}

    results = asyncio.run(_run_all_jobs())
    return {"statusCode": 200, "body": json.dumps(results)}


async def _run_miner(source_id: str, event: dict[str, Any]) -> dict[str, Any]:
    from app.services.miners.orchestrator import run_source_batch

    batch_size = int(event.get("batch_size") or 150)
    cursor = event.get("cursor")
    reset = bool(event.get("reset", False))
    try:
        return await run_source_batch(
            source_id,
            force=True,
            batch_size=batch_size,
            cursor=cursor,
            reset=reset,
        )
    except Exception as exc:
        logger.exception("Miner %s failed", source_id)
        return {"source": source_id, "error": str(exc)}


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
