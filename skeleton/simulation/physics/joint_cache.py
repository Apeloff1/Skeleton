"""Persistent deterministic joint-row impulse cache.

Joint warm-start impulses affect future solver results and are therefore
authoritative simulation state. Entries are bounded, age-limited, keyed by
stable joint/row identity, snapshot-able, and deterministic under eviction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import PhysicsValidationError

if TYPE_CHECKING:
    from .constraints import JointConstraint

MAX_JOINT_CACHE_ENTRIES = 1_000_000
MAX_JOINT_CACHE_AGE_TICKS = 10_000


def _signed_finite(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise PhysicsValidationError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class JointImpulseEntry:
    key: str
    joint_id: str
    body_a: str
    body_b: str
    row_id: str
    impulse: float
    last_tick: int

    def __post_init__(self) -> None:
        for name in ("key", "joint_id", "body_a", "body_b", "row_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise PhysicsValidationError(
                    f"joint cache {name} must be non-empty text"
                )
        if self.body_a == self.body_b:
            raise PhysicsValidationError(
                "joint cache bodies must be distinct"
            )
        if any(ord(char) < 32 for char in self.row_id) or len(self.row_id) > 128:
            raise PhysicsValidationError("invalid joint cache row_id")
        object.__setattr__(
            self,
            "impulse",
            _signed_finite(self.impulse, name="impulse"),
        )
        if (
            isinstance(self.last_tick, bool)
            or not isinstance(self.last_tick, int)
            or self.last_tick < 0
        ):
            raise PhysicsValidationError(
                "joint cache last_tick must be non-negative integer"
            )


class JointImpulseCache:
    def __init__(
        self,
        *,
        max_entries: int = 65_536,
        max_age_ticks: int = 8,
    ) -> None:
        if (
            isinstance(max_entries, bool)
            or not isinstance(max_entries, int)
            or not 1 <= max_entries <= MAX_JOINT_CACHE_ENTRIES
        ):
            raise PhysicsValidationError(
                "joint cache max_entries outside supported range"
            )
        if (
            isinstance(max_age_ticks, bool)
            or not isinstance(max_age_ticks, int)
            or not 1 <= max_age_ticks <= MAX_JOINT_CACHE_AGE_TICKS
        ):
            raise PhysicsValidationError(
                "joint cache max_age_ticks outside supported range"
            )
        self.max_entries = max_entries
        self.max_age_ticks = max_age_ticks
        self._entries: dict[str, JointImpulseEntry] = {}

    @staticmethod
    def key_for(joint_id: str, row_id: str) -> str:
        if not isinstance(joint_id, str) or not joint_id:
            raise PhysicsValidationError("joint cache joint_id must be non-empty")
        if not isinstance(row_id, str) or not row_id:
            raise PhysicsValidationError("joint cache row_id must be non-empty")
        return f"{joint_id}\x1f{row_id}"

    def __len__(self) -> int:
        return len(self._entries)

    def lookup(
        self,
        joint: JointConstraint,
        row_id: str,
        *,
        tick: int,
    ) -> JointImpulseEntry | None:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise PhysicsValidationError(
                "joint cache tick must be non-negative integer"
            )
        key = self.key_for(joint.joint_id, row_id)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if tick < entry.last_tick:
            raise PhysicsValidationError("joint cache tick regressed")
        if tick - entry.last_tick > self.max_age_ticks:
            return None
        if entry.body_a != joint.body_a or entry.body_b != joint.body_b:
            return None
        return entry

    def store(
        self,
        joint: JointConstraint,
        row_id: str,
        *,
        impulse: float,
        tick: int,
    ) -> JointImpulseEntry:
        if (
            isinstance(tick, bool)
            or not isinstance(tick, int)
            or tick < 0
        ):
            raise PhysicsValidationError(
                "joint cache tick must be non-negative integer"
            )
        key = self.key_for(joint.joint_id, row_id)
        if key not in self._entries and len(self._entries) >= self.max_entries:
            self._evict_oldest()
        entry = JointImpulseEntry(
            key=key,
            joint_id=joint.joint_id,
            body_a=joint.body_a,
            body_b=joint.body_b,
            row_id=row_id,
            impulse=impulse,
            last_tick=tick,
        )
        self._entries[key] = entry
        return entry

    def remove_joint(self, joint_id: str) -> int:
        keys = [
            key
            for key, entry in self._entries.items()
            if entry.joint_id == joint_id
        ]
        for key in sorted(keys):
            del self._entries[key]
        return len(keys)

    def remove_body(self, body_id: str) -> int:
        keys = [
            key
            for key, entry in self._entries.items()
            if entry.body_a == body_id or entry.body_b == body_id
        ]
        for key in sorted(keys):
            del self._entries[key]
        return len(keys)

    def _evict_oldest(self) -> None:
        if not self._entries:
            return
        key = min(
            self._entries,
            key=lambda item: (
                self._entries[item].last_tick,
                item,
            ),
        )
        del self._entries[key]

    def prune(self, *, tick: int) -> int:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise PhysicsValidationError(
                "joint cache tick must be non-negative integer"
            )
        stale = [
            key
            for key, entry in self._entries.items()
            if tick - entry.last_tick > self.max_age_ticks
        ]
        for key in sorted(stale):
            del self._entries[key]
        return len(stale)

    def snapshot(self) -> tuple[JointImpulseEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    def restore(self, entries: tuple[JointImpulseEntry, ...]) -> None:
        restored: dict[str, JointImpulseEntry] = {}
        try:
            entries = tuple(entries)
        except TypeError as exc:
            raise PhysicsValidationError(
                "joint cache snapshot must be iterable"
            ) from exc
        for entry in entries:
            if not isinstance(entry, JointImpulseEntry):
                raise PhysicsValidationError(
                    "joint cache snapshot contains invalid entry"
                )
            if entry.key in restored:
                raise PhysicsValidationError(
                    "joint cache snapshot contains duplicate key"
                )
            if len(restored) >= self.max_entries:
                raise PhysicsValidationError(
                    "joint cache snapshot exceeds configured bound"
                )
            restored[entry.key] = entry
        self._entries = restored

    def state_record(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "key": entry.key,
                "joint_id": entry.joint_id,
                "body_a": entry.body_a,
                "body_b": entry.body_b,
                "row_id": entry.row_id,
                "impulse": entry.impulse,
                "last_tick": entry.last_tick,
            }
            for entry in self.snapshot()
        )
