from __future__ import annotations
import asyncio
import logging
from typing import Callable, Awaitable, Optional

from gameforge.enterprise.queue import DurableQueue, QueueMessage
from gameforge.enterprise.alerts import METRICS

logger = logging.getLogger("gameforge.worker")


class QueueWorker:
    """Consumes durable queue and dispatches payloads to a handler."""

    def __init__(
        self,
        queue: DurableQueue,
        handler: Callable[[dict], Awaitable[None]],
        concurrency: int = 2,
        poll_ms: int = 500,
    ):
        self.queue = queue
        self.handler = handler
        self.concurrency = concurrency
        self.poll_ms = poll_ms
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        if self._running:
            return
        self._running = True
        for i in range(self.concurrency):
            self._tasks.append(asyncio.create_task(self._loop(i)))
        logger.info("QueueWorker started concurrency=%s", self.concurrency)

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    async def _loop(self, worker_id: int):
        while self._running:
            try:
                messages = await self.queue.consume(max_messages=1, blockout_ms=self.poll_ms)
                if not messages:
                    continue
                for msg in messages:
                    await self._handle_one(msg)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("worker-%s loop error", worker_id)
                await asyncio.sleep(0.2)

    async def _handle_one(self, msg: QueueMessage):
        try:
            await self.handler(msg.payload)
            await self.queue.ack(msg.id)
            METRICS.inc("worker_messages_total", status="ok")
            METRICS.inc("queue_acked_total")
        except Exception as e:
            logger.exception("handler failed id=%s", msg.id)
            await self.queue.nack(msg.id)
            METRICS.inc("worker_messages_total", status="error")
            METRICS.inc("queue_nacked_total")
