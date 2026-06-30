"""Redis or DynamoDB session store for voice/chat conversations."""

import json
from typing import Any, Dict, Optional

import redis.asyncio as redis

from app.config import get_settings
from app.storage.dynamo import SessionDynamoStore

settings = get_settings()


class RedisSessionStore:
    def __init__(self) -> None:
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        self._client = redis.from_url(settings.redis_url, decode_responses=True)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.close()

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def get(self, session_id: str) -> Dict[str, Any]:
        if not self._client:
            await self.connect()
        assert self._client
        raw = await self._client.get(self._key(session_id))
        return json.loads(raw) if raw else {}

    async def set(self, session_id: str, data: Dict[str, Any], ttl_seconds: int = 7200) -> None:
        if not self._client:
            await self.connect()
        assert self._client
        await self._client.set(self._key(session_id), json.dumps(data), ex=ttl_seconds)

    async def update(self, session_id: str, updates: Dict[str, Any], ttl_seconds: int = 7200) -> Dict[str, Any]:
        current = await self.get(session_id)
        current.update(updates)
        await self.set(session_id, current, ttl_seconds)
        return current

    async def delete(self, session_id: str) -> None:
        if not self._client:
            await self.connect()
        assert self._client
        await self._client.delete(self._key(session_id))


def _create_session_store():
    if settings.sessions_table:
        return SessionDynamoStore()
    return RedisSessionStore()


session_store = _create_session_store()
