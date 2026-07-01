"""Async Lambda worker invocation for long-running lead miners."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.services.mining_progress import DEFAULT_BATCH_SIZE

logger = logging.getLogger(__name__)
settings = get_settings()


def _worker_function_name() -> str:
    if settings.worker_function_name:
        return settings.worker_function_name
    env = settings.app_env
    suffix = {"development": "dev", "production": "prod", "staging": "staging"}.get(env, env)
    return f"travel-ai-worker-{suffix}"


def invoke_miner_async(
    source_id: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    cursor: Optional[int] = None,
    reset: bool = False,
) -> dict[str, Any]:
    """Queue a batched miner job on the Worker Lambda (up to 15 min)."""
    function_name = _worker_function_name()
    client = boto3.client("lambda", region_name=settings.aws_region)
    payload = json.dumps(
        {
            "job": source_id,
            "batch_size": batch_size,
            "cursor": cursor,
            "reset": reset,
        }
    )
    try:
        client.invoke(FunctionName=function_name, InvocationType="Event", Payload=payload)
    except (ClientError, BotoCoreError) as exc:
        logger.exception("Failed to invoke worker %s for %s", function_name, source_id)
        return {"queued": False, "source": source_id, "error": str(exc)}

    segment = "B2B" if source_id in {"b2b", "directories"} else "B2C"
    return {
        "queued": True,
        "source": source_id,
        "imported": 0,
        "raw_found": 0,
        "batch_size": batch_size,
        "message": (
            f"Fetching up to {batch_size} {segment} leads worldwide (batch). "
            "Progress updates in ~1–3 minutes. Use Fetch More for next batch."
        ),
    }
