"""Dedicated scraper Lambda entry points (share worker Docker image)."""

from __future__ import annotations

import json
import os
from typing import Any


def _run(job: str, event: dict[str, Any], context: Any) -> dict[str, Any]:
    from scheduled_handler import handler

    payload = {**event, "job": job}
    return handler(payload, context)


def reddit_rss_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _run("reddit_rss", event, context)


def twitter_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _run("twitter", event, context)


def telegram_groups_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _run("telegram", event, context)


def lead_scorer_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _run("score_leads", event, context)


def default_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    job = event.get("job") or os.environ.get("SCRAPER_JOB")
    if job:
        return _run(job, event, context)
    from scheduled_handler import handler

    return handler(event, context)
