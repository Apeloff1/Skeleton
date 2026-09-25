"""Index freshness state for retrieval planes.

Freshness is metadata, not authority: this registry makes stale projections
explicit and supplies a cache token that flips exactly when a configured plane
crosses its stale boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Dict, Mapping, Optional

STATE_VERSION = 1


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


@dataclass(frozen=True, slots=True)
class PlaneFreshness:
    plane: str
    index_version: str
    source_revision: str
    indexed_at: float
    stale_after_s: float

    def __post_init__(self) -> None:
        if not self.plane or not self.index_version or not self.source_revision:
            raise ValueError("plane, index_version, and source_revision are required")
        _finite("indexed_at", self.indexed_at)
        stale_after = _finite("stale_after_s", self.stale_after_s)
        if stale_after <= 0:
            raise ValueError("stale_after_s must be positive")

    def stale(self, now: float) -> bool:
        return _finite("now", now) >= self.indexed_at + self.stale_after_s

    def metadata(self, now: float) -> Dict[str, Any]:
        age_s = max(0.0, _finite("now", now) - self.indexed_at)
        return {
            "index_version": self.index_version,
            "source_revision": self.source_revision,
            "indexed_at": self.indexed_at,
            "age_s": round(age_s, 6),
            "stale": self.stale(now),
            "stale_after_s": self.stale_after_s,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plane": self.plane,
            "index_version": self.index_version,
            "source_revision": self.source_revision,
            "indexed_at": self.indexed_at,
            "stale_after_s": self.stale_after_s,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlaneFreshness":
        if not isinstance(payload, Mapping):
            raise ValueError("freshness payload must be a mapping")
        return cls(
            plane=str(payload.get("plane") or ""),
            index_version=str(payload.get("index_version") or ""),
            source_revision=str(payload.get("source_revision") or ""),
            indexed_at=_finite("indexed_at", payload.get("indexed_at")),
            stale_after_s=_finite("stale_after_s", payload.get("stale_after_s")),
        )


class FreshnessRegistry:
    """Thread-safe freshness authority for projection/index metadata."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._states: Dict[str, PlaneFreshness] = {}
        self._revision = 0
        self._lock = RLock()

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def update(
        self,
        plane: str,
        *,
        index_version: str,
        source_revision: str,
        indexed_at: Optional[float] = None,
        stale_after_s: float = 300.0,
    ) -> PlaneFreshness:
        state = PlaneFreshness(
            plane=plane,
            index_version=index_version,
            source_revision=source_revision,
            indexed_at=self._clock() if indexed_at is None else _finite("indexed_at", indexed_at),
            stale_after_s=_finite("stale_after_s", stale_after_s),
        )
        with self._lock:
            self._states[plane] = state
            self._revision += 1
        return state

    def remove(self, plane: str) -> bool:
        with self._lock:
            if plane not in self._states:
                return False
            del self._states[plane]
            self._revision += 1
            return True

    def get(self, plane: str) -> Optional[PlaneFreshness]:
        with self._lock:
            return self._states.get(plane)

    def metadata(self, plane: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            state = self._states.get(plane)
            now = self._clock()
        return state.metadata(now) if state is not None else None

    def cache_token(self) -> str:
        with self._lock:
            now = self._clock()
            rows = [
                (
                    plane,
                    state.index_version,
                    state.source_revision,
                    state.stale(now),
                )
                for plane, state in sorted(self._states.items())
            ]
            revision = self._revision
        encoded = json.dumps(
            {"revision": revision, "states": rows},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.blake2b(encoded, digest_size=12).hexdigest()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": STATE_VERSION,
                "revision": self._revision,
                "states": [
                    state.to_dict()
                    for _, state in sorted(self._states.items())
                ],
            }

    @classmethod
    def from_snapshot(
        cls,
        payload: Mapping[str, Any],
        *,
        clock: Callable[[], float] = time.time,
    ) -> "FreshnessRegistry":
        if not isinstance(payload, Mapping) or payload.get("version") != STATE_VERSION:
            raise ValueError("unsupported freshness registry state")
        revision = payload.get("revision")
        rows = payload.get("states")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("freshness revision must be a non-negative integer")
        if not isinstance(rows, list):
            raise ValueError("freshness states must be a list")
        registry = cls(clock=clock)
        seen = set()
        for row in rows:
            state = PlaneFreshness.from_dict(row)
            if state.plane in seen:
                raise ValueError("duplicate plane freshness state")
            seen.add(state.plane)
            registry._states[state.plane] = state
        registry._revision = revision
        return registry
