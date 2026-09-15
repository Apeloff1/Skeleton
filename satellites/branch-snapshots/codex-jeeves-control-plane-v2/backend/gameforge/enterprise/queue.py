from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import asyncio
import uuid


@dataclass
class QueueMessage:
    id: str
    payload: Dict[str, Any]
    attempts: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class DurableQueue(ABC):
    @abstractmethod
    async def publish(self, payload: Dict[str, Any]) -> str: ...

    @abstractmethod
    async def consume(self, max_messages: int = 1, blockout_ms: int = 1000) -> List[QueueMessage]: ...

    @abstractmethod
    async def ack(self, message_id: str) -> None: ...

    @abstractmethod
    async def nack(self, message_id: str) -> None: ...


class InMemoryDurableQueue(DurableQueue):
    def __init__(self):
        self._pending: List[QueueMessage] = []
        self._inflight: Dict[str, QueueMessage] = {}
        self._lock = asyncio.Lock()

    async def publish(self, payload: Dict[str, Any]) -> str:
        mid = str(uuid.uuid4())[:12]
        msg = QueueMessage(id=mid, payload=payload)
        async with self._lock:
            self._pending.append(msg)
        return mid

    async def consume(self, max_messages: int = 1, blockout_ms: int = 1000) -> List[QueueMessage]:
        waited = 0
        while waited <= blockout_ms:
            async with self._lock:
                if self._pending:
                    out = []
                    for _ in range(min(max_messages, len(self._pending))):
                        m = self._pending.pop(0)
                        m.attempts += 1
                        self._inflight[m.id] = m
                        out.append(m)
                    return out
            await asyncio.sleep(0.05)
            waited += 50
        return []

    async def ack(self, message_id: str) -> None:
        async with self._lock:
            self._inflight.pop(message_id, None)

    async def nack(self, message_id: str) -> None:
        async with self._lock:
            m = self._inflight.pop(message_id, None)
            if m:
                self._pending.append(m)

    def stats(self) -> Dict[str, int]:
        return {
            "pending": len(self._pending),
            "inflight": len(self._inflight),
        }


WORK_QUEUE: DurableQueue = InMemoryDurableQueue()
