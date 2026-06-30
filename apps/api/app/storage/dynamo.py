"""DynamoDB storage layer for AWS SAM deployment."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

from app.config import get_settings

settings = get_settings()


def _table(name: str):
    return boto3.resource("dynamodb").Table(name)


def _serialize(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _deserialize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    if isinstance(obj, dict):
        return {k: _deserialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deserialize(v) for v in obj]
    return obj


class DynamoStore:
    """Generic DynamoDB access for single-table design entities."""

    def __init__(self, table_name: str) -> None:
        self.table_name = table_name
        self._table = _table(table_name) if table_name else None

    @property
    def enabled(self) -> bool:
        return bool(self._table)

    def put(self, pk: str, sk: str, item: dict[str, Any], gsi1pk: str = "", gsi1sk: str = "") -> dict[str, Any]:
        assert self._table
        record = {"PK": pk, "SK": sk, **_serialize(item)}
        if gsi1pk:
            record["GSI1PK"] = gsi1pk
            record["GSI1SK"] = gsi1sk or sk
        self._table.put_item(Item=record)
        return _deserialize(record)

    def get(self, pk: str, sk: str) -> Optional[dict[str, Any]]:
        assert self._table
        resp = self._table.get_item(Key={"PK": pk, "SK": sk})
        item = resp.get("Item")
        return _deserialize(item) if item else None

    def query_pk(self, pk: str, limit: int = 50) -> list[dict[str, Any]]:
        assert self._table
        resp = self._table.query(KeyConditionExpression=Key("PK").eq(pk), Limit=limit)
        return [_deserialize(i) for i in resp.get("Items", [])]

    def query_gsi1(self, gsi1pk: str, limit: int = 50, scan_forward: bool = False) -> list[dict[str, Any]]:
        assert self._table
        resp = self._table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(gsi1pk),
            Limit=limit,
            ScanIndexForward=scan_forward,
        )
        return [_deserialize(i) for i in resp.get("Items", [])]

    def update(self, pk: str, sk: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get(pk, sk) or {"PK": pk, "SK": sk}
        current.update(_serialize(updates))
        self._table.put_item(Item=current)
        return _deserialize(current)


class SessionDynamoStore:
    """TTL-backed session store replacing Redis in AWS."""

    def __init__(self) -> None:
        self._table = _table(settings.sessions_table) if settings.sessions_table else None

    @property
    def enabled(self) -> bool:
        return bool(self._table)

    async def get(self, session_id: str) -> dict[str, Any]:
        if not self._table:
            return {}
        resp = self._table.get_item(Key={"PK": f"session:{session_id}"})
        item = resp.get("Item")
        if not item:
            return {}
        data = item.get("data", "{}")
        return json.loads(data) if isinstance(data, str) else _deserialize(data)

    async def set(self, session_id: str, data: dict[str, Any], ttl_seconds: int = 7200) -> None:
        if not self._table:
            return
        self._table.put_item(
            Item={
                "PK": f"session:{session_id}",
                "data": json.dumps(data),
                "expiresAt": int(time.time()) + ttl_seconds,
            }
        )

    async def update(self, session_id: str, updates: dict[str, Any], ttl_seconds: int = 7200) -> dict[str, Any]:
        current = await self.get(session_id)
        current.update(updates)
        await self.set(session_id, current, ttl_seconds)
        return current

    async def delete(self, session_id: str) -> None:
        if not self._table:
            return
        self._table.delete_item(Key={"PK": f"session:{session_id}"})

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass


def leads_store() -> DynamoStore:
    return DynamoStore(settings.leads_table)


def events_store() -> DynamoStore:
    return DynamoStore(settings.events_table)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
