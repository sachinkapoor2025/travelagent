"""Lead mining source configuration — stored in DynamoDB."""

from __future__ import annotations

from typing import Any

from app.storage.dynamo import events_store

DEFAULT_SOURCES: dict[str, dict[str, Any]] = {
    "reddit": {"enabled": True, "label": "Reddit", "schedule": "every 2 hours", "markets": ["uae", "india", "uk", "au", "us"]},
    "telegram": {"enabled": True, "label": "Telegram", "schedule": "every hour", "markets": ["uae", "india", "uk", "au", "us"]},
    "directories": {"enabled": True, "label": "Google Maps & Directories", "schedule": "daily 3am UTC", "markets": ["uae", "india", "uk", "au", "us"]},
    "clay": {"enabled": False, "label": "Clay Webhook", "schedule": "real-time", "markets": []},
    "apollo": {"enabled": False, "label": "Apollo Webhook", "schedule": "real-time", "markets": []},
}


def get_sources() -> dict[str, dict[str, Any]]:
    store = events_store()
    row = store.get("MINING#CONFIG", "SOURCES")
    if row and row.get("sources"):
        merged = {k: {**v, **row["sources"].get(k, {})} for k, v in DEFAULT_SOURCES.items()}
        return merged
    return {k: dict(v) for k, v in DEFAULT_SOURCES.items()}


def set_source_enabled(source_id: str, enabled: bool) -> dict[str, Any]:
    sources = get_sources()
    if source_id not in sources:
        raise KeyError(source_id)
    sources[source_id]["enabled"] = enabled
    store = events_store()
    store.put("MINING#CONFIG", "SOURCES", {"sources": sources})
    return sources


def record_run(source_id: str, stats: dict[str, Any]) -> None:
    from app.storage.dynamo import now_iso

    store = events_store()
    ts = now_iso()
    store.put(
        f"MINING#RUN#{source_id}",
        ts,
        {"source": source_id, **stats},
        gsi1pk=f"MINING#RUN#{source_id}",
        gsi1sk=ts,
    )
