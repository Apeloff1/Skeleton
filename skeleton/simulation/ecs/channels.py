"""Typed, double-buffered event channels for the live world.

Semantics follow the widely used "events live for two updates" model:

* :meth:`EventChannel.send` appends to the *current* buffer with a
  monotonically increasing sequence number.
* :meth:`EventBus.update` (called once per tick by the scheduler) drops the
  *previous* buffer and makes the current one previous.
* Readers keep a sequence cursor, so every reader sees every event exactly
  once as long as it runs at least once every two ticks, regardless of
  whether it runs before or after the sender inside a tick.

Reader cursors are owned by the bus (keyed by reader id) rather than by the
system objects, which makes them part of the snapshot: a restored world
re-delivers exactly the events the original would have.

Payloads must be plain data (:mod:`.values`) and are copied on send.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import digest
from .errors import EventError, EventOverflowError
from .values import canonical_copy, check_value, copy_value, from_json, to_json

MAX_CHANNELS = 1024
MAX_READERS = 16_384
DEFAULT_CAPACITY = 65_536
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class EventRecord:
    channel: str
    sequence: int
    tick: int
    payload: Any


class EventChannel:
    __slots__ = ("_current", "_next_sequence", "_previous", "capacity", "dropped_total", "name", "sent_total")

    def __init__(self, name: str, capacity: int = DEFAULT_CAPACITY) -> None:
        if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
            raise EventError("invalid event channel name", context={"name": name})
        if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= 1_000_000:
            raise EventError("invalid event channel capacity", context={"capacity": capacity})
        self.name = name
        self.capacity = capacity
        self._previous: list[EventRecord] = []
        self._current: list[EventRecord] = []
        self._next_sequence = 0
        self.sent_total = 0
        self.dropped_total = 0

    def __len__(self) -> int:
        return len(self._previous) + len(self._current)

    @property
    def next_sequence(self) -> int:
        return self._next_sequence

    def send(self, payload: Any, *, tick: int) -> EventRecord:
        if len(self._current) >= self.capacity:
            self.dropped_total += 1
            raise EventOverflowError("event channel full", context={"channel": self.name, "capacity": self.capacity})
        check_value(payload, label=f"event {self.name}")
        record = EventRecord(self.name, self._next_sequence, tick, canonical_copy(payload))
        self._next_sequence += 1
        self.sent_total += 1
        self._current.append(record)
        return record

    def since(self, cursor: int) -> list[EventRecord]:
        out = [r for r in self._previous if r.sequence >= cursor]
        out.extend(r for r in self._current if r.sequence >= cursor)
        return out

    def update(self) -> int:
        dropped = len(self._previous)
        self._previous = self._current
        self._current = []
        return dropped

    def clear(self) -> None:
        self._previous = []
        self._current = []

    def oldest_sequence(self) -> int:
        if self._previous:
            return self._previous[0].sequence
        if self._current:
            return self._current[0].sequence
        return self._next_sequence

    def to_record(self) -> dict[str, Any]:
        def rows(buffer: list[EventRecord]) -> list[list[Any]]:
            return [[r.sequence, r.tick, to_json(r.payload)] for r in buffer]

        return {
            "name": self.name,
            "capacity": self.capacity,
            "next_sequence": self._next_sequence,
            "sent_total": self.sent_total,
            "dropped_total": self.dropped_total,
            "previous": rows(self._previous),
            "current": rows(self._current),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> EventChannel:
        channel = cls(record["name"], record["capacity"])
        channel._next_sequence = int(record["next_sequence"])
        channel.sent_total = int(record["sent_total"])
        channel.dropped_total = int(record["dropped_total"])
        channel._previous = [EventRecord(channel.name, int(s), int(t), from_json(p)) for s, t, p in record["previous"]]
        channel._current = [EventRecord(channel.name, int(s), int(t), from_json(p)) for s, t, p in record["current"]]
        sequences = [r.sequence for r in channel._previous + channel._current]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise EventError("event channel record sequences are not monotonic", context={"channel": channel.name})
        if sequences and sequences[-1] >= channel._next_sequence:
            raise EventError("event channel record next_sequence is stale", context={"channel": channel.name})
        return channel


class EventReader:
    """A named cursor over one channel. Obtain via :meth:`EventBus.reader`."""

    __slots__ = ("bus", "channel", "reader_id")

    def __init__(self, bus: EventBus, channel: str, reader_id: str) -> None:
        self.bus = bus
        self.channel = channel
        self.reader_id = reader_id

    def read(self) -> list[EventRecord]:
        return self.bus.read(self.channel, self.reader_id)

    def payloads(self) -> list[Any]:
        return [r.payload for r in self.read()]

    def peek(self) -> list[EventRecord]:
        return self.bus.peek(self.channel, self.reader_id)

    @property
    def missed(self) -> int:
        return self.bus.missed(self.channel, self.reader_id)


class EventBus:
    def __init__(self) -> None:
        self._channels: dict[str, EventChannel] = {}
        self._cursors: dict[tuple[str, str], int] = {}
        self._missed: dict[tuple[str, str], int] = {}

    def register(self, name: str, *, capacity: int = DEFAULT_CAPACITY) -> EventChannel:
        existing = self._channels.get(name)
        if existing is not None:
            if existing.capacity != capacity:
                raise EventError("channel already registered with different capacity", context={"channel": name})
            return existing
        if len(self._channels) >= MAX_CHANNELS:
            raise EventError("event channel bound exceeded", context={"maximum": MAX_CHANNELS})
        channel = EventChannel(name, capacity)
        self._channels[name] = channel
        return channel

    def channel(self, name: str) -> EventChannel:
        try:
            return self._channels[name]
        except KeyError:
            raise EventError("unknown event channel", context={"channel": name}) from None

    def has(self, name: str) -> bool:
        return name in self._channels

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._channels))

    def send(self, name: str, payload: Any, *, tick: int) -> EventRecord:
        return self.channel(name).send(payload, tick=tick)

    def reader(self, name: str, reader_id: str) -> EventReader:
        channel = self.channel(name)
        if not isinstance(reader_id, str) or not reader_id:
            raise EventError("reader id must be non-empty text")
        key = (name, reader_id)
        if key not in self._cursors:
            if len(self._cursors) >= MAX_READERS:
                raise EventError("event reader bound exceeded")
            # New readers start at the oldest retained event, so a system
            # added mid-game still observes the current window.
            self._cursors[key] = channel.oldest_sequence()
            self._missed[key] = 0
        return EventReader(self, name, reader_id)

    def peek(self, name: str, reader_id: str) -> list[EventRecord]:
        key = (name, reader_id)
        if key not in self._cursors:
            raise EventError("unknown event reader", context={"channel": name, "reader": reader_id})
        return [
            EventRecord(r.channel, r.sequence, r.tick, copy_value(r.payload))
            for r in self.channel(name).since(self._cursors[key])
        ]

    def read(self, name: str, reader_id: str) -> list[EventRecord]:
        key = (name, reader_id)
        channel = self.channel(name)
        if key not in self._cursors:
            raise EventError("unknown event reader", context={"channel": name, "reader": reader_id})
        cursor = self._cursors[key]
        oldest = channel.oldest_sequence()
        if cursor < oldest:
            self._missed[key] += oldest - cursor
            cursor = oldest
        records = channel.since(cursor)
        self._cursors[key] = channel.next_sequence
        # Readers get private copies so one consumer cannot corrupt another.
        return [EventRecord(r.channel, r.sequence, r.tick, copy_value(r.payload)) for r in records]

    def missed(self, name: str, reader_id: str) -> int:
        return self._missed.get((name, reader_id), 0)

    def update(self) -> None:
        for name in sorted(self._channels):
            self._channels[name].update()

    def to_record(self) -> dict[str, Any]:
        return {
            "channels": [self._channels[name].to_record() for name in sorted(self._channels)],
            "cursors": [[c, r, self._cursors[(c, r)], self._missed[(c, r)]] for c, r in sorted(self._cursors)],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> EventBus:
        bus = cls()
        for row in record["channels"]:
            channel = EventChannel.from_record(row)
            bus._channels[channel.name] = channel
        for channel_name, reader_id, cursor, missed in record["cursors"]:
            if channel_name not in bus._channels:
                raise EventError("event reader references unknown channel", context={"channel": channel_name})
            bus._cursors[(channel_name, reader_id)] = int(cursor)
            bus._missed[(channel_name, reader_id)] = int(missed)
        return bus

    @property
    def fingerprint(self) -> str:
        return digest({"domain": "skeleton.simulation.ecs.live_events.v1", "bus": self.to_record()})


__all__ = ["DEFAULT_CAPACITY", "EventBus", "EventChannel", "EventReader", "EventRecord"]
