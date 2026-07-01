"""Track batched lead-mining progress in DynamoDB."""

from __future__ import annotations

from typing import Any, Optional

from app.storage.dynamo import events_store, now_iso

DEFAULT_BATCH_SIZE = 150
MARKETS_PER_LAMBDA_PASS = 6


def get_progress(source_id: str) -> dict[str, Any]:
    row = events_store().get(f"MINING#PROGRESS#{source_id}", "STATE")
    if not row:
        return _empty_progress(source_id)
    return row


def _empty_progress(source_id: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "cursor": 0,
        "total_markets": 0,
        "total_imported": 0,
        "last_batch_imported": 0,
        "last_run_at": None,
        "complete": False,
        "completed_at": None,
        "has_more": True,
        "markets_remaining": 0,
        "segment": None,
        "message": "Not started",
    }


def reset_progress(source_id: str, segment: Optional[str] = None) -> dict[str, Any]:
    state = {
        "source_id": source_id,
        "cursor": 0,
        "total_markets": 0,
        "total_imported": 0,
        "last_batch_imported": 0,
        "last_run_at": None,
        "complete": False,
        "completed_at": None,
        "segment": segment,
        "message": "Progress reset — ready for new fetch",
        "updated_at": now_iso(),
    }
    events_store().put(f"MINING#PROGRESS#{source_id}", "STATE", state)
    return state


def save_progress(source_id: str, **fields: Any) -> dict[str, Any]:
    current = get_progress(source_id)
    current.update(fields)
    current["updated_at"] = now_iso()
    events_store().put(f"MINING#PROGRESS#{source_id}", "STATE", current)
    return current
