"""Scheduled Lambda worker — hot leads, price alerts, nurture emails, lead miners."""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("travel-ai-scheduled")
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    job = event.get("job") or event.get("detail", {}).get("job")
    if job in {"reddit", "telegram", "directories"}:
        results = asyncio.run(_run_miner(job))
        return {"statusCode": 200, "body": json.dumps(results)}

    results = asyncio.run(_run_all_jobs())
    return {"statusCode": 200, "body": json.dumps(results)}


async def _run_miner(source_id: str) -> dict[str, Any]:
    from app.services.miners.orchestrator import run_source

    try:
        return await run_source(source_id)
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
