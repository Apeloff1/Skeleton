"""Persistent contact state for deterministic solver warm starting.

The cache is authoritative future-affecting simulation state: cached impulses can
change the next solver iteration, so snapshots and state digests must bind it.
Entries are bounded, age-limited, normal-alignment checked, and keyed only by
stable body/contact feature identity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .collision import ContactManifold, ContactPoint
from .errors import PhysicsValidationError
from .math3d import Vec3

MAX_CONTACT_CACHE_ENTRIES = 1_000_000
MAX_CONTACT_AGE_TICKS = 10_000


def _non_negative(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise PhysicsValidationError(f"{name} must be finite and non-negative")
    return value


@dataclass(frozen=True, slots=True)
class ContactCacheEntry:
    key: str
    body_a: str
    body_b: str
    feature_id: str
    normal: Vec3
    normal_impulse: float
    tangent: Vec3
    tangent_impulse: float
    last_tick: int

    def __post_init__(self) -> None:
        if not self.key:
            raise PhysicsValidationError("contact cache key must be non-empty")
        if self.body_a == self.body_b:
            raise PhysicsValidationError("contact cache bodies must be distinct")
        if not self.feature_id:
            raise PhysicsValidationError("contact feature id must be non-empty")
        object.__setattr__(self, "normal", self.normal.normalized())
        object.__setattr__(
            self,
            "normal_impulse",
            _non_negative(self.normal_impulse, name="normal_impulse"),
        )
        if not isinstance(self.tangent, Vec3):
            raise PhysicsValidationError("contact tangent must be Vec3")
        tangent = self.tangent.normalized_or_zero()
        object.__setattr__(self, "tangent", tangent)
        if isinstance(self.tangent_impulse, bool) or not isinstance(
            self.tangent_impulse, (int, float)
        ):
            raise PhysicsValidationError("tangent_impulse must be numeric")
        tangent_impulse = float(self.tangent_impulse)
        if not math.isfinite(tangent_impulse):
            raise PhysicsValidationError("tangent_impulse must be finite")
        if tangent.length_squared() == 0.0 and abs(tangent_impulse) > 0.0:
            raise PhysicsValidationError("zero tangent cannot carry tangent impulse")
        object.__setattr__(self, "tangent_impulse", tangent_impulse)
        if isinstance(self.last_tick, bool) or not isinstance(self.last_tick, int) or self.last_tick < 0:
            raise PhysicsValidationError("last_tick must be a non-negative integer")


class ContactCache:
    def __init__(
        self,
        *,
        max_entries: int = 65_536,
        max_age_ticks: int = 8,
        normal_alignment: float = 0.85,
    ) -> None:
        if (
            isinstance(max_entries, bool)
            or not isinstance(max_entries, int)
            or not 1 <= max_entries <= MAX_CONTACT_CACHE_ENTRIES
        ):
            raise PhysicsValidationError("contact cache max_entries outside supported range")
        if (
            isinstance(max_age_ticks, bool)
            or not isinstance(max_age_ticks, int)
            or not 1 <= max_age_ticks <= MAX_CONTACT_AGE_TICKS
        ):
            raise PhysicsValidationError("contact cache max_age_ticks outside supported range")
        if (
            isinstance(normal_alignment, bool)
            or not isinstance(normal_alignment, (int, float))
            or not math.isfinite(float(normal_alignment))
            or not 0.0 <= float(normal_alignment) <= 1.0
        ):
            raise PhysicsValidationError("contact cache normal_alignment must be in [0, 1]")
        self.max_entries = max_entries
        self.max_age_ticks = max_age_ticks
        self.normal_alignment = float(normal_alignment)
        self._entries: dict[str, ContactCacheEntry] = {}

    @staticmethod
    def key_for(manifold: ContactManifold, point: ContactPoint) -> str:
        return (
            f"{manifold.body_a}\x1f{manifold.body_b}\x1f"
            f"{point.feature_id}"
        )

    def __len__(self) -> int:
        return len(self._entries)

    def lookup(
        self,
        manifold: ContactManifold,
        point: ContactPoint,
        *,
        tick: int,
    ) -> ContactCacheEntry | None:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise PhysicsValidationError("contact cache tick must be non-negative integer")
        key = self.key_for(manifold, point)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if tick < entry.last_tick:
            raise PhysicsValidationError("contact cache tick regressed")
        if tick - entry.last_tick > self.max_age_ticks:
            return None
        if entry.normal.dot(manifold.normal) < self.normal_alignment:
            return None
        return entry

    def store(
        self,
        manifold: ContactManifold,
        point: ContactPoint,
        *,
        normal_impulse: float,
        tangent: Vec3 = Vec3(),
        tangent_impulse: float = 0.0,
        tick: int,
    ) -> ContactCacheEntry:
        key = self.key_for(manifold, point)
        if key not in self._entries and len(self._entries) >= self.max_entries:
            self._evict_oldest()
        entry = ContactCacheEntry(
            key=key,
            body_a=manifold.body_a,
            body_b=manifold.body_b,
            feature_id=point.feature_id,
            normal=manifold.normal,
            normal_impulse=normal_impulse,
            tangent=tangent,
            tangent_impulse=tangent_impulse,
            last_tick=tick,
        )
        self._entries[key] = entry
        return entry

    def remove_body(self, body_id: str) -> int:
        removed = [
            key
            for key, entry in self._entries.items()
            if entry.body_a == body_id or entry.body_b == body_id
        ]
        for key in sorted(removed):
            del self._entries[key]
        return len(removed)

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
            raise PhysicsValidationError("contact cache tick must be non-negative integer")
        stale = [
            key
            for key, entry in self._entries.items()
            if tick - entry.last_tick > self.max_age_ticks
        ]
        for key in sorted(stale):
            del self._entries[key]
        return len(stale)

    def snapshot(self) -> tuple[ContactCacheEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    def restore(self, entries: tuple[ContactCacheEntry, ...]) -> None:
        restored: dict[str, ContactCacheEntry] = {}
        for entry in entries:
            if not isinstance(entry, ContactCacheEntry):
                raise PhysicsValidationError("contact cache snapshot contains invalid entry")
            if entry.key in restored:
                raise PhysicsValidationError("contact cache snapshot contains duplicate key")
            if len(restored) >= self.max_entries:
                raise PhysicsValidationError("contact cache snapshot exceeds configured bound")
            restored[entry.key] = entry
        self._entries = restored

    def state_record(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "key": entry.key,
                "body_a": entry.body_a,
                "body_b": entry.body_b,
                "feature_id": entry.feature_id,
                "normal": entry.normal.to_tuple(),
                "normal_impulse": entry.normal_impulse,
                "tangent": entry.tangent.to_tuple(),
                "tangent_impulse": entry.tangent_impulse,
                "last_tick": entry.last_tick,
            }
            for entry in self.snapshot()
        )
