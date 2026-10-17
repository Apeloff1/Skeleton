"""In-process realtime hub: subscribe, fan-out, bounded replay, presence.

Implements ADR ``docs/architecture/ADR-realtime-transport.md`` (PR #4101):

* **One monotonic id sequence per hub stream** shared by every channel, so a
  single ``Last-Event-ID`` / ``?cursor=`` resumes all subscribed channels.
  The sequence is seeded from wall-clock microseconds at hub start, so ids
  keep increasing across restarts and a pre-restart cursor is never confused
  with a post-restart event: it simply ages out (``stream.reset``).
* **Bounded replay ring**: a cursor still inside the ring replays what was
  missed; an aged-out cursor gets ``stream.reset`` and the client refetches
  state over REST.
* **Bounded per-subscriber queue, drop-oldest**: on overflow the oldest queued
  events for that subscriber are discarded and a single ``stream.lagged
  {dropped}`` is queued ahead of the survivors. The client reconnects from its
  last delivered id and the ring fills the gap. Publishers never block.
* ``publish`` is thread-safe: job workers may publish from other threads
  while the event loop streams to clients.
* **Secret guard** on every publish (#3637).
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from .envelope import (
    CHANNEL_PRESENCE,
    CHANNELS,
    STREAM_LAGGED,
    STREAM_RESET,
    ControlEvent,
    EnvelopeError,
    RealtimeEvent,
    ts_from_ms,
    validate_channel,
    validate_identifier,
)
from .guard import PayloadSecretGuard, RealtimeSecretError
from .slo import RealtimeSLO

Frame = Union[RealtimeEvent, ControlEvent]
Authorizer = Callable[[str, str], bool]

PRESENCE_ACTIONS = ("join", "heartbeat", "leave")
DEFAULT_SCOPE = "app"


class RealtimeAuthError(PermissionError):
    """Principal may not subscribe to / act on the requested channel."""


def _default_authorizer(principal: str, channel: str) -> bool:
    # The API gate has already verified the HMAC seal; any verified principal
    # may read the app-wide live channels. Deployments can narrow this hook.
    return bool(principal)


def _wall_ms() -> float:
    return time.time() * 1000.0


class Subscription:
    """One connected consumer; binds to the event loop that first awaits it."""

    def __init__(
        self,
        hub: "RealtimeHub",
        channels: Tuple[str, ...],
        principal: str,
        max_queue: int,
        job_id: Optional[str] = None,
    ) -> None:
        self.id = uuid.uuid4().hex
        self.hub = hub
        self.channels = channels
        self.principal = principal
        self.job_id = job_id
        self.max_queue = max_queue
        self.head_at_connect = 0
        self.replayed = 0
        self.dropped = 0
        self._queue: Deque[Frame] = deque()
        self._events_queued = 0
        self._closed = False
        try:
            self._loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._wake = asyncio.Event() if self._loop is not None else None

    @property
    def closed(self) -> bool:
        return self._closed

    def wants(self, event: RealtimeEvent) -> bool:
        if event.channel not in self.channels:
            return False
        if self.job_id is not None and event.channel != CHANNEL_PRESENCE:
            return event.job_id == self.job_id
        return True

    # -- producer side (hub lock held) ------------------------------------
    def _offer(self, event: RealtimeEvent) -> int:
        """Queue an event; on overflow drop the oldest. Returns events dropped."""
        if self._closed:
            return 0
        dropped = 0
        first_dropped: Optional[int] = None
        while self._events_queued >= self.max_queue:
            for index, item in enumerate(self._queue):
                if isinstance(item, RealtimeEvent):
                    del self._queue[index]
                    self._events_queued -= 1
                    dropped += 1
                    if first_dropped is None and item.type != "presence.snapshot":
                        first_dropped = item.seq
                    break
            else:  # pragma: no cover - defensive
                break
        if dropped:
            self.dropped += dropped
            lagged = next(
                (f for f in self._queue if isinstance(f, ControlEvent) and f.type == STREAM_LAGGED),
                None,
            )
            payload: Dict[str, Any] = {"dropped": dropped}
            if first_dropped is not None:
                # Additive field: a client with no cursor yet resumes here.
                payload["resume_from"] = str(first_dropped - 1)
            if lagged is not None:
                self._queue.remove(lagged)
                payload["dropped"] = int(lagged.payload.get("dropped", 0)) + dropped
                if "resume_from" in lagged.payload:
                    payload["resume_from"] = lagged.payload["resume_from"]
            self._queue.appendleft(ControlEvent(type=STREAM_LAGGED, ts=ts_from_ms(_wall_ms()), payload=payload))
        self._queue.append(event)
        self._events_queued += 1
        self._notify()
        return dropped

    def _push_control(self, frame: ControlEvent) -> None:
        self._queue.append(frame)
        self._notify()

    def _close(self) -> None:
        if not self._closed:
            self._closed = True
            self._notify()

    def _notify(self) -> None:
        if self._wake is None or self._loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._wake.set()
        elif not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._wake.set)
            except RuntimeError:
                pass

    # -- consumer side -----------------------------------------------------
    def _pop(self) -> Frame:
        frame = self._queue.popleft()
        if isinstance(frame, RealtimeEvent):
            self._events_queued -= 1
        return frame

    def drain(self) -> List[Frame]:
        with self.hub._lock:
            items = list(self._queue)
            self._queue.clear()
            self._events_queued = 0
            return items

    async def next(self, timeout: Optional[float] = None) -> Optional[Frame]:
        """Next frame, ``None`` on timeout. Raises ``EOFError`` once closed and empty."""
        while True:
            with self.hub._lock:
                if self._wake is None:
                    # Bind lazily: subscriptions may be opened from a sync
                    # (threadpool) handler and consumed on the event loop.
                    self._loop = asyncio.get_running_loop()
                    self._wake = asyncio.Event()
                if self._queue:
                    return self._pop()
                if self._closed:
                    raise EOFError("subscription closed")
                self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout)
            except asyncio.TimeoutError:
                return None


@dataclass
class PresenceMember:
    client_id: str
    principal: str
    scope: str
    joined_at: str
    last_seen_ms: float
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "scope": self.scope,
            "joined_at": self.joined_at,
            "last_seen": ts_from_ms(self.last_seen_ms),
            "meta": self.meta,
        }


class RealtimeHub:
    """Fan-out hub with resumable replay, drop-oldest backpressure and presence."""

    def __init__(
        self,
        *,
        replay_capacity: int = 4096,
        subscriber_queue: int = 512,
        heartbeat_interval_s: float = 15.0,
        presence_ttl_s: float = 45.0,
        max_subscribers: int = 10_000,
        guard: Optional[PayloadSecretGuard] = None,
        slo: Optional[RealtimeSLO] = None,
        authorizer: Optional[Authorizer] = None,
        clock_ms: Callable[[], float] = _wall_ms,
        id_seed: Optional[int] = None,
    ) -> None:
        if replay_capacity < 1 or subscriber_queue < 1:
            raise ValueError("replay_capacity and subscriber_queue must be >= 1")
        self.replay_capacity = int(replay_capacity)
        self.subscriber_queue = int(subscriber_queue)
        self.heartbeat_interval_s = float(heartbeat_interval_s)
        self.presence_ttl_s = float(presence_ttl_s)
        self.max_subscribers = int(max_subscribers)
        self.guard = guard or PayloadSecretGuard()
        self.slo = slo or RealtimeSLO()
        self.authorizer: Authorizer = authorizer or _default_authorizer
        self._clock = clock_ms
        self._lock = threading.RLock()
        self._ring: Deque[RealtimeEvent] = deque(maxlen=self.replay_capacity)
        self._seq = int(id_seed) if id_seed is not None else int(time.time() * 1_000_000)
        self._seed = self._seq
        self._subs: Dict[str, Subscription] = {}
        self._presence: Dict[Tuple[str, str], PresenceMember] = {}
        self._closed = False
        self._sweeper: Optional[asyncio.Task] = None

    # -- introspection -----------------------------------------------------
    @property
    def head_id(self) -> str:
        return str(self._seq)

    @property
    def head_seq(self) -> int:
        return self._seq

    def _ts(self) -> str:
        return ts_from_ms(self._clock())

    # -- publish -----------------------------------------------------------
    def publish(
        self,
        channel: str,
        event_type: str,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        job_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> RealtimeEvent:
        """Validate, secret-scrub, store and fan out one event. Thread-safe."""
        try:
            validate_channel(channel)
            clean, hits = self.guard.scrub(payload or {})
        except RealtimeSecretError:
            self.slo.record_publish_rejected("secret")
            raise
        except EnvelopeError:
            self.slo.record_publish_rejected("invalid")
            raise
        self.slo.record_redactions(hits)
        lagged: List[int] = []
        with self._lock:
            if self._closed:
                raise RuntimeError("hub is closed")
            try:
                event = RealtimeEvent(
                    id=str(self._seq + 1),
                    ts=self._ts(),
                    channel=channel,
                    type=event_type,
                    payload=clean,
                    job_id=job_id,
                    correlation_id=correlation_id,
                )
            except EnvelopeError:
                self.slo.record_publish_rejected("invalid")
                raise
            self._seq += 1
            self._ring.append(event)
            for sub in self._subs.values():
                if sub.wants(event):
                    dropped = sub._offer(event)
                    if dropped:
                        lagged.append(dropped)
        self.slo.record_published(channel)
        for dropped in lagged:
            self.slo.record_lagged(dropped)
        return event

    # -- subscribe ---------------------------------------------------------
    def subscribe(
        self,
        channels: Iterable[str],
        *,
        principal: str,
        cursor: Optional[int] = None,
        job_id: Optional[str] = None,
    ) -> Subscription:
        """Register a consumer; replays from ``cursor`` (exclusive) when retained."""
        wanted = tuple(dict.fromkeys(validate_channel(c) for c in channels))
        if not wanted:
            raise EnvelopeError(f"subscribe needs at least one channel from {CHANNELS}")
        validate_identifier(job_id, "job_id")
        denied = [c for c in wanted if not self.authorizer(principal, c)]
        if denied:
            self.slo.record_connect(False)
            raise RealtimeAuthError(f"principal may not subscribe to {denied}")
        reset_reason: Optional[str] = None
        with self._lock:
            if self._closed or len(self._subs) >= self.max_subscribers:
                self.slo.record_connect(False)
                raise RuntimeError("realtime hub closed or at subscriber capacity")
            sub = Subscription(self, wanted, principal, self.subscriber_queue, job_id)
            sub.head_at_connect = self._seq
            if cursor is not None:
                oldest = self._ring[0].seq if self._ring else self._seq + 1
                if cursor > self._seq:
                    reset_reason = "cursor_ahead_of_stream"
                elif cursor + 1 < oldest and cursor < self._seq:
                    reset_reason = "cursor_aged_out"
                else:
                    backlog = [e for e in self._ring if e.seq > cursor and sub.wants(e)]
                    # Replay is bounded by the ring, not the live queue: widen
                    # this subscriber's bound by its backlog so a lagged
                    # client can always resume what the ring still holds.
                    sub.max_queue = self.subscriber_queue + len(backlog)
                    sub._queue.extend(backlog)
                    sub._events_queued = len(backlog)
                    sub.replayed = len(backlog)
                if reset_reason is not None:
                    sub._queue.append(
                        ControlEvent(
                            type=STREAM_RESET,
                            ts=self._ts(),
                            payload={
                                "reason": reset_reason,
                                "cursor": str(cursor),
                                "head_id": str(self._seq),
                                "oldest_id": self._ring[0].id if self._ring else None,
                            },
                        )
                    )
            if CHANNEL_PRESENCE in wanted:
                sub._queue.append(self._snapshot_event_locked())
                sub._events_queued += 1
            self._subs[sub.id] = sub
            active = len(self._subs)
        self.slo.record_connect(True)
        self.slo.set_active_connections(active)
        if cursor is not None:
            self.slo.record_resume(reset_reason is None)
            self.slo.record_resumed(sub.replayed)
        return sub

    def unsubscribe(self, sub: Subscription, *, reason: str = "closed") -> None:
        with self._lock:
            removed = self._subs.pop(sub.id, None)
            sub._close()
            active = len(self._subs)
        if removed is not None:
            self.slo.record_disconnect(reason)
        self.slo.set_active_connections(active)

    # -- presence ----------------------------------------------------------
    def _snapshot_event_locked(self, scope: Optional[str] = None) -> RealtimeEvent:
        """Per-subscriber presence.snapshot. Not stored; carries the head id."""
        members = sorted(
            (m.to_dict() for m in self._presence.values() if scope is None or m.scope == scope),
            key=lambda m: (m["scope"], m["client_id"]),
        )
        return RealtimeEvent(
            id=str(max(self._seq, 1)),
            ts=self._ts(),
            channel=CHANNEL_PRESENCE,
            type="presence.snapshot",
            payload={"members": members, "count": len(members)},
        )

    def _check_presence(self, principal: str, client_id: str, scope: str) -> None:
        validate_identifier(client_id, "client_id")
        validate_identifier(scope, "scope")
        if not self.authorizer(principal, CHANNEL_PRESENCE):
            raise RealtimeAuthError("principal may not use presence")

    def presence(
        self,
        action: str,
        *,
        client_id: str,
        principal: str,
        scope: str = DEFAULT_SCOPE,
        meta: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """``POST /api/v1/presence`` semantics: join | heartbeat | leave."""
        if action not in PRESENCE_ACTIONS:
            raise EnvelopeError(f"action must be one of {PRESENCE_ACTIONS}")
        self._check_presence(principal, client_id, scope)
        if action == "leave":
            self._leave(client_id, principal, scope, reason="left")
        else:
            self._touch(client_id, principal, scope, meta, announce=True)
        return self.presence_snapshot(scope)

    def _touch(self, client_id: str, principal: str, scope: str, meta: Optional[Mapping[str, Any]], *, announce: bool) -> PresenceMember:
        clean_meta, hits = self.guard.scrub(meta or {})
        self.slo.record_redactions(hits)
        now = self._clock()
        with self._lock:
            key = (scope, client_id)
            existing = self._presence.get(key)
            if existing is not None and existing.principal != principal:
                raise RealtimeAuthError("client_id is held by another principal")
            if existing is not None:
                existing.last_seen_ms = now
                if meta:
                    existing.meta = clean_meta
                return existing
            member = PresenceMember(client_id, principal, scope, ts_from_ms(now), now, clean_meta)
            self._presence[key] = member
        if announce:
            self.publish(CHANNEL_PRESENCE, "presence.joined", member.to_dict())
        return member

    def _leave(self, client_id: str, principal: str, scope: str, *, reason: str) -> bool:
        with self._lock:
            member = self._presence.get((scope, client_id))
            if member is None or member.principal != principal:
                return False
            del self._presence[(scope, client_id)]
        payload = member.to_dict()
        payload["reason"] = reason
        self.publish(CHANNEL_PRESENCE, "presence.left", payload)
        return True

    def sweep_presence(self, now_ms: Optional[float] = None) -> List[PresenceMember]:
        """Expire members silent for longer than ``presence_ttl_s``."""
        now = self._clock() if now_ms is None else float(now_ms)
        cutoff = now - self.presence_ttl_s * 1000.0
        with self._lock:
            expired = [m for m in self._presence.values() if m.last_seen_ms < cutoff]
            for m in expired:
                self._presence.pop((m.scope, m.client_id), None)
        for m in expired:
            payload = m.to_dict()
            payload["reason"] = "heartbeat_timeout"
            self.slo.record_presence_timeout()
            self.publish(CHANNEL_PRESENCE, "presence.left", payload)
        return expired

    def presence_snapshot(self, scope: str = DEFAULT_SCOPE) -> Dict[str, Any]:
        validate_identifier(scope, "scope")
        with self._lock:
            members = sorted((m.to_dict() for m in self._presence.values() if m.scope == scope), key=lambda m: m["client_id"])
            head = str(self._seq)
        return {"scope": scope, "members": members, "count": len(members), "head_id": head}

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Start the presence sweeper on the running loop (idempotent)."""
        if self._sweeper is not None and not self._sweeper.done():
            return
        interval = max(0.05, self.presence_ttl_s / 3.0)

        async def _sweep() -> None:
            while not self._closed:
                await asyncio.sleep(interval)
                try:
                    self.sweep_presence()
                except Exception:
                    pass

        self._sweeper = asyncio.get_running_loop().create_task(_sweep())

    async def aclose(self) -> None:
        with self._lock:
            self._closed = True
            subs = list(self._subs.values())
            self._subs.clear()
            for sub in subs:
                sub._close()
        if self._sweeper is not None:
            self._sweeper.cancel()
            try:
                await self._sweeper
            except (asyncio.CancelledError, Exception):
                pass
        self.slo.set_active_connections(0)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "kind": "realtime-hub",
                "head_id": str(self._seq),
                "oldest_id": self._ring[0].id if self._ring else None,
                "retained": len(self._ring),
                "replay_capacity": self.replay_capacity,
                "subscriber_queue": self.subscriber_queue,
                "subscribers": len(self._subs),
                "presence_members": len(self._presence),
                "heartbeat_interval_s": self.heartbeat_interval_s,
                "presence_ttl_s": self.presence_ttl_s,
                "closed": self._closed,
            }


__all__ = [
    "DEFAULT_SCOPE",
    "Frame",
    "PRESENCE_ACTIONS",
    "PresenceMember",
    "RealtimeAuthError",
    "RealtimeHub",
    "Subscription",
]
