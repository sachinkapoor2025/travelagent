"""DynamoDB storage layer — serverless, pay-per-request."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

from app.config import get_settings

settings = get_settings()


@lru_cache
def _resource():
    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint
        key = settings.aws_access_key_id or "local"
        secret = settings.aws_secret_access_key or "local"
        kwargs["aws_access_key_id"] = key
        kwargs["aws_secret_access_key"] = secret
    elif settings.aws_access_key_id and settings.aws_access_key_id not in ("local", ""):
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.resource("dynamodb", **kwargs)


def _table(name: str):
    return _resource().Table(name)


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
    def __init__(self, table_name: str) -> None:
        self.table_name = table_name
        self._table = None

    @property
    def enabled(self) -> bool:
        return bool(self.table_name)

    def _get_table(self):
        if self._table is None and self.table_name:
            self._table = _table(self.table_name)
        return self._table

    def put(self, pk: str, sk: str, item: dict[str, Any], gsi1pk: str = "", gsi1sk: str = "") -> dict[str, Any]:
        table = self._get_table()
        assert table
        record = {"PK": pk, "SK": sk, **_serialize(item)}
        if gsi1pk:
            record["GSI1PK"] = gsi1pk
            record["GSI1SK"] = gsi1sk or sk
        self._table.put_item(Item=record)
        return _deserialize(record)

    def get(self, pk: str, sk: str) -> Optional[dict[str, Any]]:
        table = self._get_table()
        assert table
        resp = table.get_item(Key={"PK": pk, "SK": sk})
        item = resp.get("Item")
        return _deserialize(item) if item else None

    def query_pk(self, pk: str, limit: int = 50) -> list[dict[str, Any]]:
        table = self._get_table()
        assert table
        resp = table.query(KeyConditionExpression=Key("PK").eq(pk), Limit=limit)
        return [_deserialize(i) for i in resp.get("Items", [])]

    def query_gsi1(self, gsi1pk: str, limit: int = 50, scan_forward: bool = False) -> list[dict[str, Any]]:
        table = self._get_table()
        assert table
        resp = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(gsi1pk),
            Limit=limit,
            ScanIndexForward=scan_forward,
        )
        return [_deserialize(i) for i in resp.get("Items", [])]

    def update(self, pk: str, sk: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get(pk, sk) or {"PK": pk, "SK": sk}
        merged = {**current, **_serialize(updates)}
        table = self._get_table()
        assert table
        table.put_item(Item=merged)
        return _deserialize(merged)


class SessionDynamoStore:
    def __init__(self) -> None:
        self._table_name = settings.sessions_table
        self._table = None

    def _get_table(self):
        if self._table is None and self._table_name:
            self._table = _table(self._table_name)
        return self._table

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def get(self, session_id: str) -> dict[str, Any]:
        table = self._get_table()
        if not table:
            return {}
        resp = table.get_item(Key={"PK": f"session:{session_id}"})
        item = resp.get("Item")
        if not item:
            return {}
        data = item.get("data", "{}")
        return json.loads(data) if isinstance(data, str) else _deserialize(data)

    async def set(self, session_id: str, data: dict[str, Any], ttl_seconds: int = 7200) -> None:
        table = self._get_table()
        if not table:
            return
        table.put_item(
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
        table = self._get_table()
        if not table:
            return
        table.delete_item(Key={"PK": f"session:{session_id}"})


def leads_store() -> DynamoStore:
    return DynamoStore(settings.leads_table)


def bookings_store() -> DynamoStore:
    return DynamoStore(settings.bookings_table)


def events_store() -> DynamoStore:
    return DynamoStore(settings.events_table)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
