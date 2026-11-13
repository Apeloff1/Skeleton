"""GF-P0-16: exact game environment adapters, deterministic replay, holdout isolation.

Builds on :class:`skeleton.simulation.world_model.EnvironmentAdapter`; does not
fork it. All buffers are bounded (see GF-P0-18 resource envelopes).
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import math
import re
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from skeleton.simulation.world_model import EnvironmentAdapter


class EnvironmentMismatchError(RuntimeError):
    """Requested environment identity does not exactly match the registered one."""


class HoldoutLeakError(RuntimeError):
    """A holdout example was routed into training/replay data."""


MAX_RECORD_BYTES = 1 << 20
MAX_EPISODE_STEPS = 10000
MAX_PAYLOAD_DEPTH = 32
MAX_ENCODED_ITEMS = 50000


def _validate_json_shape(value: object) -> None:
    """Bound nesting and element count *before* JSON generation begins.

    JSON can silently coerce non-string object keys and it can construct very
    large intermediate strings before a post-serialization byte check. Only
    exact JSON-compatible primitives/containers are admitted. Shared values
    are allowed; cycles cannot pass the bounded depth traversal.
    """
    pending: list[tuple[object, int]] = [(value, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if visited > MAX_ENCODED_ITEMS or depth > MAX_PAYLOAD_DEPTH:
            raise ValueError("replay JSON node/depth budget exhausted")
        if type(item) is dict:
            if len(item) > MAX_ENCODED_ITEMS - visited:
                raise ValueError("replay JSON node budget exhausted")
            for key, child in item.items():
                if type(key) is not str or len(key) > MAX_RECORD_BYTES:
                    raise ValueError("replay JSON requires bounded string keys")
                pending.append((child, depth + 1))
        elif type(item) in (tuple, list):
            if len(item) > MAX_ENCODED_ITEMS - visited:
                raise ValueError("replay JSON node budget exhausted")
            pending.extend((child, depth + 1) for child in item)
        elif item is None or type(item) is bool:
            continue
        elif type(item) is str:
            if len(item) > MAX_RECORD_BYTES:
                raise ValueError("replay JSON string exceeds byte budget")
        elif type(item) is int:
            # Far more than ordinary JSON number precision, but rejects a
            # pathological integer before expensive decimal conversion.
            if item.bit_length() > 16384:
                raise ValueError("replay JSON integer exceeds numeric budget")
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("replay requires finite JSON numbers")
        else:
            raise ValueError("replay requires strict canonical JSON data")


def _canonical(value: object) -> bytes:
    """Canonical, alias-free bytes under hard element, depth and byte bounds."""
    _validate_json_shape(value)
    payload = bytearray()
    try:
        encoder = json.JSONEncoder(
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        )
        for chunk in encoder.iterencode(value):
            # ensure_ascii guarantees ASCII. Check character count first so
            # an oversized single string chunk is never copied to the buffer.
            if len(chunk) > MAX_RECORD_BYTES - len(payload):
                raise ValueError("replay payload exceeds strict byte bound")
            payload.extend(chunk.encode("ascii"))
    except (TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("replay requires strict canonical JSON data") from exc
    return bytes(payload)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class EnvironmentIdentity:
    simulation_id: str
    build_digest: str
    seed: int

    def __post_init__(self) -> None:
        if (type(self.simulation_id) is not str or
                re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.simulation_id) is None or
                type(self.build_digest) is not str or
                re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", self.build_digest) is None or
                type(self.seed) is not int or not 0 <= self.seed <= 2**64 - 1):
            raise ValueError("invalid exact bounded environment identity")

    def key(self) -> str:
        return f"{self.simulation_id}@{self.build_digest}#{self.seed}"


class ExactEnvironmentRegistry:
    """Only returns an adapter whose simulation id, build digest and seed match exactly."""

    def __init__(self, *, max_environments: int = 256) -> None:
        if type(max_environments) is not int or not 1 <= max_environments <= 4096:
            raise ValueError("max_environments must be a bounded positive integer")
        self.max_environments = max_environments
        self._items: dict[str, tuple[EnvironmentIdentity, EnvironmentAdapter]] = {}
        self._lock = threading.RLock()

    def register(self, identity: EnvironmentIdentity, adapter: EnvironmentAdapter) -> None:
        if not isinstance(identity, EnvironmentIdentity):
            raise TypeError("registry requires exact EnvironmentIdentity")
        if not isinstance(adapter, EnvironmentAdapter):
            raise TypeError("adapter does not implement EnvironmentAdapter")
        if (type(adapter.simulation_id) is not str
                or type(adapter.seed) is not int
                or adapter.simulation_id != identity.simulation_id
                or adapter.seed != identity.seed):
            raise EnvironmentMismatchError("adapter does not match declared identity")
        with self._lock:
            if identity.key() not in self._items and len(self._items) >= self.max_environments:
                raise RuntimeError("environment registry capacity exhausted")
            if identity.key() in self._items and self._items[identity.key()][1] is not adapter:
                raise EnvironmentMismatchError("cannot silently replace exact registered environment")
            self._items[identity.key()] = (identity, adapter)

    def resolve(self, identity: EnvironmentIdentity) -> EnvironmentAdapter:
        if not isinstance(identity, EnvironmentIdentity):
            raise TypeError("resolution requires exact EnvironmentIdentity")
        with self._lock:
            entry = self._items.get(identity.key())
            if entry is None:
                raise EnvironmentMismatchError(f"no exact environment for {identity.key()}")
            registered, adapter = entry
            # A previously admitted adapter is mutable. Refuse a lookup if
            # its identifier or seed has drifted since the registration.
            if (registered != identity
                    or type(adapter.simulation_id) is not str
                    or type(adapter.seed) is not int
                    or adapter.simulation_id != identity.simulation_id
                    or adapter.seed != identity.seed):
                raise EnvironmentMismatchError("registered adapter identity changed")
            return adapter


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    example_id: str
    environment_key: str
    payload_digest: str
    payload: Mapping[str, Any]


class HoldoutSplit:
    """Deterministic hash-based split; holdout ids can never enter training data."""

    def __init__(self, *, salt: str, holdout_fraction: float) -> None:
        if (type(holdout_fraction) not in (int, float)
                or not math.isfinite(holdout_fraction) or not 0.0 < holdout_fraction < 1.0):
            raise ValueError("holdout_fraction must be finite and in (0,1)")
        if type(salt) is not str or not 1 <= len(salt) <= 256:
            raise ValueError("bounded salt is required")
        self.salt = salt
        self.holdout_fraction = holdout_fraction

    def is_holdout(self, example_id: str) -> bool:
        if type(example_id) is not str or not 1 <= len(example_id) <= 256:
            raise ValueError("invalid bounded example identifier")
        h = hashlib.sha256(f"{self.salt}:{example_id}".encode()).digest()
        return int.from_bytes(h[:8], "big") / 2**64 < self.holdout_fraction


class BoundedRecordBuffer:
    """FIFO record store capped by item count; evicts oldest on overflow."""

    def __init__(self, *, max_items: int, max_bytes: int | None = None) -> None:
        if type(max_items) is not int or not 1 <= max_items <= 100000:
            raise ValueError("max_items must be bounded")
        if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= 256*1024*1024):
            raise ValueError("max_bytes must be bounded")
        self.max_items = max_items
        self.max_bytes = max_bytes if max_bytes is not None else 4 * 1024 * 1024
        self.retained_bytes = 0
        self._records: deque[ReplayRecord] = deque()
        self._lock = threading.RLock()
        self.evicted = 0

    @staticmethod
    def _size(record: ReplayRecord) -> int:
        return len(_canonical(dict(record.payload)))

    def _append(self, record: ReplayRecord) -> None:
        if (not isinstance(record, ReplayRecord)
                or type(record.example_id) is not str
                or not 1 <= len(record.example_id) <= 256
                or type(record.environment_key) is not str
                or not 1 <= len(record.environment_key) <= 512
                or type(record.payload_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", record.payload_digest) is None
                or not isinstance(record.payload, Mapping)):
            raise ValueError("invalid replay record descriptor")
        # Snapshot and verify before admitting; callers cannot poison retention
        # or sampling after insertion by mutating the source dictionary.
        if len(record.payload) > MAX_ENCODED_ITEMS:
            raise ValueError("replay mapping exceeds element budget")
        normalized = json.loads(_canonical(dict(record.payload)))
        digest = _digest(normalized)
        if digest != record.payload_digest:
            raise ValueError("replay payload digest mismatch")
        stored = ReplayRecord(record.example_id, record.environment_key, digest, normalized)
        size = self._size(stored)
        if size > self.max_bytes:
            raise ValueError("record exceeds buffer byte envelope")
        with self._lock:
            self._records.append(stored)
            self.retained_bytes += size
            while len(self._records) > self.max_items or self.retained_bytes > self.max_bytes:
                self.retained_bytes -= self._size(self._records.popleft())
                self.evicted += 1

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def _records_locked(self) -> tuple[ReplayRecord, ...]:
        return tuple(
            ReplayRecord(
                record.example_id, record.environment_key, record.payload_digest,
                json.loads(_canonical(record.payload)),
            )
            for record in self._records
        )

    def _digest_locked(self) -> str:
        # Preserve json.dumps(sort_keys=True, separators=(",", ":")) digest
        # compatibility while avoiding a materialized 100k-item list and a
        # second full deep-copy of each retained record.
        digest = hashlib.sha256()
        digest.update(b"[")
        for index, record in enumerate(self._records):
            if index:
                digest.update(b",")
            digest.update(_canonical((record.example_id, record.payload_digest)))
        digest.update(b"]")
        return digest.hexdigest()

    def records(self) -> tuple[ReplayRecord, ...]:
        with self._lock:
            return self._records_locked()

    def digest(self) -> str:
        with self._lock:
            return self._digest_locked()


class HoldoutBuffer(BoundedRecordBuffer):
    def __init__(self, split: HoldoutSplit, *, max_items: int, max_bytes: int | None = None) -> None:
        super().__init__(max_items=max_items, max_bytes=max_bytes)
        self.split = split

    def add(self, record: ReplayRecord) -> None:
        if not isinstance(record, ReplayRecord):
            raise ValueError("invalid holdout record")
        if not self.split.is_holdout(record.example_id):
            raise HoldoutLeakError("non-holdout example routed to holdout buffer")
        self._append(record)


class DeterministicReplayBuffer(BoundedRecordBuffer):
    """Training replay; rejects holdout ids and samples reproducibly from a seed."""

    def __init__(self, split: HoldoutSplit, *, max_items: int, max_bytes: int | None = None) -> None:
        super().__init__(max_items=max_items, max_bytes=max_bytes)
        self.split = split

    def add(self, record: ReplayRecord) -> None:
        if not isinstance(record, ReplayRecord):
            raise ValueError("invalid replay record")
        if self.split.is_holdout(record.example_id):
            raise HoldoutLeakError("holdout example routed to training replay")
        self._append(record)

    def sample(self, k: int, *, seed: int) -> tuple[ReplayRecord, ...]:
        if (type(k) is not int or not 0 <= k <= 100000
                or type(seed) is not int or not 0 <= seed < 2**256):
            raise ValueError("bounded reproducible sampling coordinates required")
        # The sample and its randomness seed must refer to the SAME buffer
        # generation. Two independent reads could race a writer/eviction and
        # silently assign a different replay digest to the returned records.
        with self._lock:
            items = self._records_locked()
            snapshot_digest = self._digest_locked()
        rng = random.Random(f"{seed}:{snapshot_digest}")
        return tuple(rng.sample(items, min(k, len(items))))


def buffers_for_envelope(
    split: HoldoutSplit, envelope: Any, *, max_items: int, holdout_share: float = 0.25
) -> tuple[DeterministicReplayBuffer, HoldoutBuffer]:
    """Split a ``ResourceEnvelope.max_buffer_bytes`` budget across replay/holdout."""

    if (type(holdout_share) not in (int, float) or not math.isfinite(holdout_share)
            or not 0.0 < holdout_share < 1.0):
        raise ValueError("holdout_share must be finite in (0,1)")
    if (type(envelope.max_buffer_bytes) is not int or not 2 <= envelope.max_buffer_bytes <= 256*1024*1024):
        raise ValueError("invalid shared replay memory byte envelope")
    hold_bytes = max(1, int(envelope.max_buffer_bytes * holdout_share))
    replay_bytes = max(1, envelope.max_buffer_bytes - hold_bytes)
    return (
        DeterministicReplayBuffer(split, max_items=max_items, max_bytes=replay_bytes),
        HoldoutBuffer(split, max_items=max_items, max_bytes=hold_bytes),
    )


def route_records(
    records: Iterable[ReplayRecord],
    replay: DeterministicReplayBuffer,
    holdout: HoldoutBuffer,
) -> None:
    if replay.split is not holdout.split:
        raise ValueError("replay and holdout must share one split")
    for index, record in enumerate(records):
        if index >= 100000:
            raise ValueError("replay route batch exceeded bounded admission")
        if not isinstance(record, ReplayRecord):
            raise ValueError("invalid routed record")
        (holdout if replay.split.is_holdout(record.example_id) else replay).add(record)


def make_record(example_id: str, identity: EnvironmentIdentity, payload: Mapping[str, Any]) -> ReplayRecord:
    if type(example_id) is not str or not 1 <= len(example_id) <= 256:
        raise ValueError("invalid bounded replay example identity")
    if not isinstance(identity, EnvironmentIdentity) or not isinstance(payload, Mapping):
        raise ValueError("invalid replay source identity or payload")
    if len(payload) > MAX_ENCODED_ITEMS:
        raise ValueError("replay payload mapping exceeds element budget")
    copied = json.loads(_canonical(dict(payload)))
    return ReplayRecord(example_id, identity.key(), _digest(copied), copied)


def replay_episode(
    adapter: EnvironmentAdapter, actions: Iterable[Mapping[str, object]]
) -> str:
    """Reset and replay actions; returns a digest of the state trajectory."""

    if not isinstance(adapter, EnvironmentAdapter):
        raise ValueError("replay requires a certified EnvironmentAdapter protocol")
    states = [_digest(dict(adapter.reset()))]
    for index, action in enumerate(actions):
        if index >= MAX_EPISODE_STEPS:
            raise ValueError("deterministic episode step budget exhausted")
        if not isinstance(action, Mapping):
            raise ValueError("invalid action source")
        safe_action = json.loads(_canonical(dict(action)))
        adapter.step(safe_action)
        states.append(_digest(dict(adapter.state)))
    return _digest(states)


__all__ = [
    "BoundedRecordBuffer", "buffers_for_envelope", "DeterministicReplayBuffer", "EnvironmentIdentity",
    "EnvironmentMismatchError", "ExactEnvironmentRegistry", "HoldoutBuffer",
    "HoldoutLeakError", "HoldoutSplit", "ReplayRecord", "make_record",
    "replay_episode", "route_records",
]
