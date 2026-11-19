"""Authoritative per-frame engine GPS position + streamed map/nav update hooks (GF-P0-130).

The engine is authoritative: each frame submits one position per tracked
entity for a given ``(console, era)`` lane. The hub validates the fix, keeps
frame numbers strictly monotonic per lane, fans the update out to registered
map/navigation hooks and appends a hash-chained :class:`FrameProof` so any
consumer can verify that no frame was dropped, reordered or rewritten.

:class:`FramePositionSource` feeds typed frames into that same hub. A fix
whose coordinates do not fall in its declared chunk is rejected, and the
streamed navigation cursor must stay ordered and gap-free. ``submit_frame``
itself is unchanged and may still be used by callers that are not a stream.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Protocol

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


@dataclass(frozen=True)
class FrameFix:
    """One entity fix taken from a typed frame, with the chunk that frame claims."""

    entity_id: str
    x: float
    y: float
    z: float = 0.0
    heading_deg: float = 0.0
    region: str = ""
    chunk_xy: tuple[int, int] = (0, 0)

    def as_position(self) -> PositionFix:
        return PositionFix(
            self.entity_id, self.x, self.y, self.z, self.heading_deg, self.region
        )


@dataclass(frozen=True)
class TypedFrame:
    """One authoritative frame of fictional GPS fixes for a registered lane."""

    console: str
    era: str
    frame: int
    fixes: tuple[FrameFix, ...]
    chunk_size_m: float = 32.0


class FramePositionSource(Protocol):
    """Supplies typed frames in stream order. A missing frame is not invented."""

    def frames(self) -> Iterable[TypedFrame]:
        """Yield typed frames. Holes must be absent so the cursor can fail closed."""


@dataclass(frozen=True)
class NavigationCursor:
    """Streamed per-lane frame index. Ordered, starting at 0, with no gaps."""

    console: str
    era: str
    frames: tuple[int, ...]
    head_hash: str

    def __post_init__(self) -> None:
        if any(type(frame) is not int or frame < 0 for frame in self.frames):
            raise GPSRejected("navigation cursor frame invalid")
        if self.frames and self.frames[0] != 0:
            raise GPSRejected("navigation cursor must start at frame 0")
        for prev, nxt in zip(self.frames, self.frames[1:]):
            if nxt != prev + 1:
                raise GPSRejected("navigation cursor is not ordered and gap-free")


def _chunk_cell(x: float, y: float, chunk_size_m: float) -> tuple[int, int]:
    return (math.floor(x / chunk_size_m), math.floor(y / chunk_size_m))


@dataclass
class FrameGPSHub:
    """Per-lane authoritative GPS stream. ``lanes`` lists allowed (console, era) pairs."""

    lanes: frozenset[tuple[str, str]]
    max_speed_per_frame: float = math.inf
    _hooks: list[Hook] = field(default_factory=list)
    _last_frame: dict[tuple[str, str], int] = field(default_factory=dict)
    _last_pos: dict[tuple[str, str, str], PositionFix] = field(default_factory=dict)
    _proofs: dict[tuple[str, str], list[FrameProof]] = field(default_factory=dict)
    _stream_frames: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    _stream_head: dict[tuple[str, str], str] = field(default_factory=dict)

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

    def stream_cursor(self, console: str, era: str) -> NavigationCursor:
        lane = (console, era)
        if lane not in self.lanes:
            raise GPSRejected(f"lane {console}/{era} not registered")
        return NavigationCursor(
            console, era, tuple(self._stream_frames.get(lane, ())),
            self._stream_head.get(lane, GENESIS),
        )

    def accept_frames(self, source: FramePositionSource) -> tuple[NavigationCursor, ...]:
        """Feed typed frames. Reject chunk disagreement and cursor gaps before commit."""
        try:
            stream = source.frames()
        except AttributeError as exc:
            raise GPSRejected("FramePositionSource must provide frames()") from exc
        typed_frames = tuple(stream)
        expected = {lane: self._last_frame.get(lane, -1) for lane in self.lanes}
        touched: list[tuple[str, str]] = []
        for typed in typed_frames:
            if not isinstance(typed, TypedFrame):
                raise GPSRejected("typed frame required")
            lane = (typed.console, typed.era)
            if lane not in self.lanes:
                raise GPSRejected(f"lane {typed.console}/{typed.era} not registered")
            if not self._stream_frames.get(lane) and self._last_frame.get(lane, -1) >= 0:
                raise GPSRejected(
                    f"navigation cursor on {typed.console}/{typed.era} must be streamed from frame 0"
                )
            self._reject_bad_membership(typed)
            nxt = expected[lane] + 1
            if type(typed.frame) is not int or typed.frame != nxt:
                raise GPSRejected(
                    f"navigation cursor gap on {typed.console}/{typed.era}: "
                    f"expected {nxt}, got {typed.frame}"
                )
            expected[lane] = typed.frame
            if lane not in touched:
                touched.append(lane)
        for typed in typed_frames:
            update = self.submit_frame(
                typed.console,
                typed.era,
                typed.frame,
                [fix.as_position() for fix in typed.fixes],
            )
            lane = (typed.console, typed.era)
            self._stream_frames.setdefault(lane, []).append(typed.frame)
            self._stream_head[lane] = update.proof_hash
        return tuple(self.stream_cursor(console, era) for console, era in touched)

    @staticmethod
    def _reject_bad_membership(typed: TypedFrame) -> None:
        size = typed.chunk_size_m
        if (
            isinstance(size, bool)
            or not isinstance(size, (int, float))
            or not math.isfinite(size)
            or not 0.1 <= float(size) <= 1e5
        ):
            raise GPSRejected("chunk size invalid")
        if isinstance(typed.frame, bool) or not isinstance(typed.frame, int) or typed.frame < 0:
            raise GPSRejected("frame index invalid")
        for fix in typed.fixes:
            if not isinstance(fix, FrameFix):
                raise GPSRejected("typed frame fix required")
            xy = fix.chunk_xy
            if (
                not isinstance(xy, tuple)
                or len(xy) != 2
                or type(xy[0]) is not int
                or type(xy[1]) is not int
            ):
                raise GPSRejected("chunk membership must be an integer pair")
            try:
                cell = _chunk_cell(fix.x, fix.y, float(size))
            except (TypeError, ValueError, OverflowError) as exc:
                raise GPSRejected(f"{fix.entity_id} position is not a finite chunk coordinate") from exc
            if cell != xy:
                raise GPSRejected(
                    f"{fix.entity_id} position disagrees with chunk membership {xy}"
                )

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
