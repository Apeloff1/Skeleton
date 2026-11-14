"""Resilient realtime subscriber: reconnect, backoff, resume, liveness.

Usage::

    client = RealtimeClient(SSETransport(base_url, headers=mint_seal_headers),
                            channels=("build", "agent"))
    async for event in client.events():
        handle(event)

Behaviour (ADR-realtime-transport §4):

* resumes from the last delivered ``id`` via ``Last-Event-ID`` (and
  ``?cursor=``) on every reconnect, de-duplicating anything at or below it;
* ``stream.lagged`` -> immediate reconnect from the last id (the server ring
  fills the gap); ``stream.reset`` -> ``on_reset`` callback, cursor moves to
  the server head, caller refetches state over REST;
* 45 s with no bytes -> stream is dead, reconnect;
* failures back off with full jitter via ``RetryPolicy`` (0.5 s .. 30 s),
  honouring ``retry:`` as a floor and resetting after 60 s healthy;
* 401/403 (:class:`RealtimeAuthError`), 503 ``seal_unavailable``
  (:class:`RealtimeSealUnavailable`) and any connect error with
  ``retryable=False`` (e.g. 422) are raised immediately, never retried;
* ``stream.reauth`` (server max stream lifetime, S2-4) -> reconnect
  immediately from the same cursor; the transport mints a fresh seal on
  every ``open`` and the backoff is neither advanced nor slept;
* abandoning the generator (``aclose()`` / ``break``) closes the open stream.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Callable, Dict, Optional, Sequence, Union

from skeleton.realtime.envelope import CHANNELS, STREAM_LAGGED, STREAM_REAUTH, STREAM_RESET, ControlEvent, RealtimeEvent

from .backoff import ReconnectBackoff
from .errors import (
    RealtimeAuthError,
    RealtimeConnectError,
    RealtimeGaveUp,
    RealtimeProtocolError,
    RealtimeSealUnavailable,
)
from .transport import HEARTBEAT, RealtimeTransport

DEAD_STREAM_SECONDS = 45.0

Frame = Union[RealtimeEvent, ControlEvent]


class RealtimeClient:
    def __init__(
        self,
        transport: RealtimeTransport,
        *,
        channels: Sequence[str] = CHANNELS,
        job_id: Optional[str] = None,
        cursor: Optional[str] = None,
        backoff: Optional[ReconnectBackoff] = None,
        dead_stream_s: float = DEAD_STREAM_SECONDS,
        on_reset: Optional[Callable[[ControlEvent], Any]] = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.transport = transport
        self.channels = tuple(channels)
        self.job_id = job_id
        self.last_event_id: Optional[str] = cursor
        self.backoff = backoff or ReconnectBackoff()
        self.dead_stream_s = float(dead_stream_s)
        self.on_reset = on_reset
        self._sleep = sleep
        self._clock = clock
        self._closed = False
        self.stats: Dict[str, int] = {
            "connect_attempts": 0,
            "connects": 0,
            "connect_failures": 0,
            "reconnects": 0,
            "heartbeat_misses": 0,
            "events": 0,
            "duplicates_skipped": 0,
            "lagged": 0,
            "resets": 0,
            "reauths": 0,
        }

    def close(self) -> None:
        self._closed = True

    @property
    def _last_seq(self) -> int:
        return int(str(self.last_event_id).split("-", 1)[0]) if self.last_event_id else 0

    async def _next(self, iterator: AsyncIterator[Any]) -> Any:
        return await asyncio.wait_for(iterator.__anext__(), timeout=self.dead_stream_s)

    async def frames(self) -> AsyncIterator[Frame]:
        """Yield every v1 envelope and control event, reconnecting forever."""
        ever_connected = False
        while not self._closed:
            immediate = False
            self.stats["connect_attempts"] += 1
            try:
                stream = await self.transport.open(channels=self.channels, job_id=self.job_id, cursor=self.last_event_id)
            except (RealtimeAuthError, RealtimeSealUnavailable):
                self.stats["connect_failures"] += 1
                raise
            except RealtimeConnectError as exc:
                self.stats["connect_failures"] += 1
                if not exc.retryable:
                    raise
                await self._backoff_or_give_up()
                continue
            except OSError:
                self.stats["connect_failures"] += 1
                await self._backoff_or_give_up()
                continue
            self.stats["connects"] += 1
            if ever_connected:
                self.stats["reconnects"] += 1
            ever_connected = True
            opened = self._clock()
            iterator = stream.__aiter__()
            try:
                while not self._closed:
                    try:
                        item = await self._next(iterator)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        self.stats["heartbeat_misses"] += 1
                        break
                    self.backoff.honour_retry(getattr(stream, "retry_ms", None))
                    self.backoff.note_healthy(self._clock() - opened)
                    if item is HEARTBEAT:
                        continue
                    if isinstance(item, ControlEvent):
                        # Update resume state before handing the frame out.
                        if item.type == STREAM_LAGGED:
                            self.stats["lagged"] += 1
                            if self.last_event_id is None and item.payload.get("resume_from"):
                                self.last_event_id = str(item.payload["resume_from"])
                            yield item
                            immediate = True
                            break
                        if item.type == STREAM_REAUTH:
                            self.stats["reauths"] = self.stats.get("reauths", 0) + 1
                            yield item
                            immediate = True
                            break
                        if item.type == STREAM_RESET:
                            self.stats["resets"] += 1
                            head = item.payload.get("head_cursor") or item.payload.get("head_id")
                            self.last_event_id = str(head) if head else None
                            if self.on_reset is not None:
                                result = self.on_reset(item)
                                if asyncio.iscoroutine(result):
                                    await result
                        yield item
                        continue
                    if item.type == "presence.snapshot":
                        yield item
                        continue
                    if item.seq <= self._last_seq:
                        self.stats["duplicates_skipped"] += 1
                        continue
                    raw = getattr(stream, "last_id", None)
                    self.last_event_id = raw if raw and str(raw).split("-", 1)[0] == item.id else item.id
                    self.stats["events"] += 1
                    yield item
            except (RealtimeProtocolError, RealtimeConnectError, OSError):
                pass
            finally:
                # Runs on normal exit and when the consumer abandons the
                # generator (GeneratorExit at a ``yield``): close the frame
                # iterator first so its body iterator is awaited, then the
                # stream itself.
                closer = getattr(iterator, "aclose", None)
                if closer is not None:
                    try:
                        await closer()
                    except Exception:
                        pass
                await stream.aclose()
            if self._closed:
                return
            if self._clock() - opened >= self.backoff.healthy_reset_s:
                self.backoff.reset()
            if not immediate:
                await self._backoff_or_give_up()

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        """Only envelopes (control events are handled internally)."""
        async for frame in self.frames():
            if isinstance(frame, RealtimeEvent):
                yield frame

    async def _backoff_or_give_up(self) -> None:
        if self.backoff.exhausted:
            raise RealtimeGaveUp(f"gave up after {self.backoff.attempt} consecutive failures")
        await self._sleep(self.backoff.next_delay())


__all__ = ["DEAD_STREAM_SECONDS", "RealtimeClient"]
