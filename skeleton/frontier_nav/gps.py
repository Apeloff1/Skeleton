"""Authoritative per-frame engine GPS position + streamed map/nav update hooks (GF-P0-130).

The engine is authoritative: each frame submits one position per tracked
entity for a given ``(console, era)`` lane. The hub validates the fix, keeps
frame numbers strictly monotonic per lane, fans the update out to registered
map/navigation hooks and appends a hash-chained :class:`FrameProof` so any
consumer can verify that no frame was dropped, reordered or rewritten.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field

GENESIS = "0" * 64


class GPSRejected(ValueError):
    """Raised when a fix or frame violates the authoritative GPS contract."""


@dataclass(frozen=True)
class PositionFix:
    entity_id: str
    x: float
    y: float
    z: float = 0.0
    heading_deg: float = 0.0
    region: str = ""

    def validate(self) -> None:
        if not self.entity_id:
            raise GPSRejected("entity_id required")
        for name in ("x", "y", "z", "heading_deg"):
            if not math.isfinite(getattr(self, name)):
                raise GPSRejected(f"{name} must be finite")


@dataclass(frozen=True)
class NavUpdate:
    console: str
    era: str
    frame: int
    fixes: tuple[PositionFix, ...]
    proof_hash: str


@dataclass(frozen=True)
class FrameProof:
    console: str
    era: str
    frame: int
    prev_hash: str
    digest: str


def _digest(
    console: str, era: str, frame: int, prev: str, fixes: Iterable[PositionFix]
) -> str:
    body = json.dumps(
        {
            "c": console,
            "e": era,
            "f": frame,
            "p": prev,
            "x": [asdict(f) for f in fixes],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode()).hexdigest()


Hook = Callable[[NavUpdate], None]


@dataclass
class FrameGPSHub:
    """Per-lane authoritative GPS stream. ``lanes`` lists allowed (console, era) pairs."""

    lanes: frozenset[tuple[str, str]]
    max_speed_per_frame: float = math.inf
    _hooks: list[Hook] = field(default_factory=list)
    _last_frame: dict[tuple[str, str], int] = field(default_factory=dict)
    _last_pos: dict[tuple[str, str, str], PositionFix] = field(default_factory=dict)
    _proofs: dict[tuple[str, str], list[FrameProof]] = field(default_factory=dict)

    def subscribe(self, hook: Hook) -> Callable[[], None]:
        self._hooks.append(hook)
        return lambda: self._hooks.remove(hook) if hook in self._hooks else None

    def position(self, console: str, era: str, entity_id: str) -> PositionFix | None:
        return self._last_pos.get((console, era, entity_id))

    def proofs(self, console: str, era: str) -> tuple[FrameProof, ...]:
        return tuple(self._proofs.get((console, era), ()))

    def submit_frame(
        self, console: str, era: str, frame: int, fixes: Iterable[PositionFix]
    ) -> NavUpdate:
        lane = (console, era)
        if lane not in self.lanes:
            raise GPSRejected(f"lane {console}/{era} not registered")
        last = self._last_frame.get(lane, -1)
        if frame <= last:
            raise GPSRejected(f"frame {frame} not after {last}")
        batch = tuple(sorted(fixes, key=lambda f: f.entity_id))
        seen: set[str] = set()
        for fix in batch:
            fix.validate()
            if fix.entity_id in seen:
                raise GPSRejected(f"duplicate entity {fix.entity_id} in frame")
            seen.add(fix.entity_id)
            prev = self._last_pos.get((console, era, fix.entity_id))
            if prev is not None and last >= 0:
                dist = math.dist((prev.x, prev.y, prev.z), (fix.x, fix.y, fix.z))
                if dist > self.max_speed_per_frame * (frame - last):
                    raise GPSRejected(f"{fix.entity_id} teleported {dist:.2f} units")
        chain = self._proofs.setdefault(lane, [])
        prev_hash = chain[-1].digest if chain else GENESIS
        digest = _digest(console, era, frame, prev_hash, batch)
        chain.append(FrameProof(console, era, frame, prev_hash, digest))
        self._last_frame[lane] = frame
        for fix in batch:
            self._last_pos[(console, era, fix.entity_id)] = fix
        update = NavUpdate(console, era, frame, batch, digest)
        for hook in list(self._hooks):
            hook(update)
        return update

    @staticmethod
    def verify_chain(
        proofs: Iterable[FrameProof], updates: Iterable[NavUpdate]
    ) -> bool:
        prev = GENESIS
        for proof, upd in zip(proofs, updates, strict=True):
            if proof.prev_hash != prev or proof.frame != upd.frame:
                return False
            if (
                _digest(upd.console, upd.era, upd.frame, prev, upd.fixes)
                != proof.digest
            ):
                return False
            prev = proof.digest
        return True
