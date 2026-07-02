"""Lead mining source configuration — stored in DynamoDB."""

from __future__ import annotations

from typing import Any

from app.storage.dynamo import events_store

DEFAULT_SOURCES: dict[str, dict[str, Any]] = {
    "reddit_rss": {
        "enabled": True,
        "label": "Reddit RSS · buyer intent (no API key)",
        "schedule": "every 2 hours",
        "segment": "b2c",
        "markets": "worldwide",
        "priority": 1,
    },
    "telegram": {
        "enabled": True,
        "label": "Telegram Groups · real traveler questions",
        "schedule": "every 30 minutes",
        "segment": "b2c",
        "markets": "UAE, UK, AU, US diaspora",
        "priority": 1,
    },
    "twitter": {
        "enabled": True,
        "label": "Twitter/X · flight intent search",
        "schedule": "every 3 hours",
        "segment": "b2c",
        "markets": "worldwide",
        "priority": 2,
    },
    "b2c": {
        "enabled": True,
        "label": "B2C bundle · Reddit RSS + Telegram + Twitter",
        "schedule": "on demand · batched",
        "segment": "b2c",
        "markets": "worldwide",
        "priority": 1,
    },
    "reddit": {
        "enabled": False,
        "label": "Reddit OAuth (legacy — use Reddit RSS)",
        "schedule": "disabled",
        "segment": "b2c",
        "markets": "worldwide",
        "priority": 99,
    },
    "b2b": {
        "enabled": True,
        "label": "B2B · Travel Agencies (Global Directories)",
        "schedule": "on demand · batched",
        "segment": "b2b",
        "markets": "worldwide",
        "priority": 50,
    },
    "directories": {
        "enabled": True,
        "label": "Google Maps & Directories (B2B only)",
        "schedule": "daily 3am UTC",
        "segment": "b2b",
        "markets": "worldwide",
        "priority": 50,
    },
    "clay": {"enabled": False, "label": "Clay Webhook (B2B)", "schedule": "real-time", "segment": "b2b", "markets": []},
    "apollo": {"enabled": False, "label": "Apollo Webhook (B2B)", "schedule": "real-time", "segment": "b2b", "markets": []},
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
