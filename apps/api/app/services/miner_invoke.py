"""Async Lambda worker invocation for long-running lead miners."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _worker_function_name() -> str:
    if settings.worker_function_name:
        return settings.worker_function_name
    env = settings.app_env
    suffix = {"development": "dev", "production": "prod", "staging": "staging"}.get(env, env)
    return f"travel-ai-worker-{suffix}"


def invoke_miner_async(source_id: str) -> dict[str, Any]:
    """Queue a miner job on the Worker Lambda (180s timeout, all markets)."""
    function_name = _worker_function_name()
    client = boto3.client("lambda", region_name=settings.aws_region)
    payload = json.dumps({"job": source_id})
    try:
        client.invoke(FunctionName=function_name, InvocationType="Event", Payload=payload)
    except (ClientError, BotoCoreError) as exc:
        logger.exception("Failed to invoke worker %s for %s", function_name, source_id)
        return {"queued": False, "source": source_id, "error": str(exc)}

    return {
        "queued": True,
        "source": source_id,
        "imported": 0,
        "raw_found": 0,
        "message": (
            f"Fetching {source_id} leads across all markets in the background. "
            "Refresh the dashboard in 30–60 seconds."
        ),
    }
