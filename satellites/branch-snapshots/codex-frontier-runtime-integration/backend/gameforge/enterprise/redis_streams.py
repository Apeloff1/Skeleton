from __future__ import annotations
import os
import json
import uuid
from typing import Any, Dict, List, Optional

from gameforge.enterprise.queue import DurableQueue, QueueMessage


class RedisStreamsQueue(DurableQueue):
    """
    Redis Streams consumer-group queue.
    Env:
      GAMEFORGE_REDIS_URL=redis://localhost:6379/0
      GAMEFORGE_REDIS_STREAM=gameforge:work
      GAMEFORGE_REDIS_GROUP=gameforge-workers
    """

    def __init__(
        self,
        url: Optional[str] = None,
        stream: Optional[str] = None,
        group: Optional[str] = None,
        consumer: Optional[str] = None,
    ):
        self.url = url or os.getenv("GAMEFORGE_REDIS_URL", "redis://localhost:6379/0")
        self.stream = stream or os.getenv("GAMEFORGE_REDIS_STREAM", "gameforge:work")
        self.group = group or os.getenv("GAMEFORGE_REDIS_GROUP", "gameforge-workers")
        self.consumer = consumer or os.getenv("GAMEFORGE_REDIS_CONSUMER", f"c-{uuid.uuid4().hex[:8]}")
        self._redis = None

    async def connect(self):
        import redis.asyncio as redis

        self._redis = redis.from_url(self.url, decode_responses=True)
        try:
            await self._redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception:
            # group exists
            pass
        return self

    async def close(self):
        if self._redis:
            await self._redis.close()

    async def publish(self, payload: Dict[str, Any]) -> str:
        assert self._redis
        mid = await self._redis.xadd(self.stream, {"data": json.dumps(payload)})
        return str(mid)

    async def consume(self, max_messages: int = 1, blockout_ms: int = 1000) -> List[QueueMessage]:
        assert self._redis
        rows = await self._redis.xreadgroup(
            groupname=self.group,
            consumername=self.consumer,
            streams={self.stream: ">"},
            count=max_messages,
            block=blockout_ms,
        )
        out: List[QueueMessage] = []
        if not rows:
            return out
        for _stream, messages in rows:
            for mid, fields in messages:
                data = fields.get("data") or "{}"
                try:
                    payload = json.loads(data)
                except Exception:
                    payload = {"raw": data}
                out.append(QueueMessage(id=str(mid), payload=payload, attempts=1))
        return out

    async def ack(self, message_id: str) -> None:
        assert self._redis
        await self._redis.xack(self.stream, self.group, message_id)

    async def nack(self, message_id: str) -> None:
        # leave pending for reclaim; optional xclaim path later
        return

    async def reclaim(self, min_idle_ms: int = 60_000, count: int = 10) -> List[QueueMessage]:
        assert self._redis
        try:
            rows = await self._redis.xautoclaim(
                name=self.stream,
                groupname=self.group,
                consumername=self.consumer,
                min_idle_time=min_idle_ms,
                start_id="0-0",
                count=count,
            )
        except Exception:
            return []
        out: List[QueueMessage] = []
        # redis-py returns (next_id, messages, deleted)
        messages = rows[1] if isinstance(rows, (list, tuple)) and len(rows) > 1 else []
        for mid, fields in messages or []:
            data = (fields or {}).get("data") or "{}"
            try:
                payload = json.loads(data)
            except Exception:
                payload = {"raw": data}
            out.append(QueueMessage(id=str(mid), payload=payload, attempts=2))
        return out


async def build_work_queue():
    url = os.getenv("GAMEFORGE_REDIS_URL")
    if url:
        q = RedisStreamsQueue(url=url)
        await q.connect()
        return q
    from gameforge.enterprise.queue import InMemoryDurableQueue

    return InMemoryDurableQueue()
