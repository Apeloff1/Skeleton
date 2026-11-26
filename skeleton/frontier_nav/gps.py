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
import re
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
        """Feed typed frames. Reject chunk disagreement and cursor gaps before commit.

        The commit loop is atomic: if a later frame fails inside ``submit_frame``,
        the hub's frame cursor, proofs, positions, and stream head are restored.
        """
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
        snapshot = self._accept_snapshot()
        try:
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
        except Exception:
            self._restore_accept_snapshot(snapshot)
            raise

    def _accept_snapshot(
        self,
    ) -> tuple[dict, dict, dict, dict, dict]:
        """Copy the fields a streamed batch commits. ``submit_frame`` stays single-frame."""
        return (
            dict(self._last_frame),
            dict(self._last_pos),
            {lane: list(chain) for lane, chain in self._proofs.items()},
            {lane: list(frames) for lane, frames in self._stream_frames.items()},
            dict(self._stream_head),
        )

    def _restore_accept_snapshot(self, snapshot: tuple[dict, dict, dict, dict, dict]) -> None:
        last_frame, last_pos, proofs, stream_frames, stream_head = snapshot
        self._last_frame.clear()
        self._last_frame.update(last_frame)
        self._last_pos.clear()
        self._last_pos.update(last_pos)
        self._proofs.clear()
        self._proofs.update({lane: list(chain) for lane, chain in proofs.items()})
        self._stream_frames.clear()
        self._stream_frames.update(
            {lane: list(frames) for lane, frames in stream_frames.items()}
        )
        self._stream_head.clear()
        self._stream_head.update(stream_head)

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


# ---------------------------------------------------------------------------
# Fictional map layers, portals and minimap camera (GF-P0-131).
#
# Tile coordinates belong to an authored game world. This section does not
# read device location, GNSS, or Earth datums, and it does not change the
# per-frame GPS hub above.
# ---------------------------------------------------------------------------

FICTIONAL_LAYER_KINDS = ("underground", "surface", "sky-island")
MINIMAP_ZOOMS = (1, 2, 4, 8, 16)
_LAYER_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def _map_id(value: object, name: str) -> str:
    if type(value) is not str or _LAYER_ID.fullmatch(value) is None:
        raise GPSRejected(f"{name} must be a fictional map id")
    return value


def _tile_span(value: object, name: str) -> int:
    if type(value) is not int or not 1 <= value <= 4096:
        raise GPSRejected(f"{name} must be 1..4096 tiles")
    return value


@dataclass(frozen=True)
class FictionalMapLayer:
    """One authored level of a fictional world: underground, surface, or sky-island."""

    layer_id: str
    kind: str
    width: int
    height: int
    elevation_m: float

    def __post_init__(self) -> None:
        _map_id(self.layer_id, "layer_id")
        _tile_span(self.width, "width")
        _tile_span(self.height, "height")
        if type(self.elevation_m) not in (int, float) or not math.isfinite(self.elevation_m):
            raise GPSRejected("elevation_m must be finite")
        if abs(self.elevation_m) > 1_000_000:
            raise GPSRejected("elevation_m out of fictional range")
        expected = _kind_for_elevation(float(self.elevation_m))
        if self.kind != expected:
            raise GPSRejected(
                f"layer kind {self.kind} does not match fictional elevation {self.elevation_m}"
            )


def _kind_for_elevation(elevation_m: float) -> str:
    if elevation_m < 0:
        return "underground"
    if elevation_m >= 120:
        return "sky-island"
    return "surface"


@dataclass(frozen=True)
class FictionalPortal:
    """A declared link between two fictional layers. Endpoints are tile indexes."""

    portal_id: str
    source_layer: str
    source_x: int
    source_y: int
    dest_layer: str
    dest_x: int
    dest_y: int
    bidirectional: bool = True

    def __post_init__(self) -> None:
        _map_id(self.portal_id, "portal_id")
        _map_id(self.source_layer, "source_layer")
        _map_id(self.dest_layer, "dest_layer")
        for name in ("source_x", "source_y", "dest_x", "dest_y"):
            if type(getattr(self, name)) is not int:
                raise GPSRejected(f"{name} must be an integer tile")
        if type(self.bidirectional) is not bool:
            raise GPSRejected("bidirectional must be boolean")


def validate_fictional_portals(
    layers: Iterable[FictionalMapLayer], portals: Iterable[FictionalPortal]
) -> tuple[FictionalPortal, ...]:
    by_id = {}
    for layer in layers:
        if layer.layer_id in by_id:
            raise GPSRejected(f"duplicate layer {layer.layer_id}")
        by_id[layer.layer_id] = layer
    seen: set[str] = set()
    checked: list[FictionalPortal] = []
    for portal in portals:
        if portal.portal_id in seen:
            raise GPSRejected(f"duplicate portal {portal.portal_id}")
        seen.add(portal.portal_id)
        _endpoint(by_id, portal.source_layer, portal.source_x, portal.source_y, portal.portal_id)
        _endpoint(by_id, portal.dest_layer, portal.dest_x, portal.dest_y, portal.portal_id)
        checked.append(portal)
    return tuple(checked)


def _endpoint(
    layers: dict[str, FictionalMapLayer], layer_id: str, x: int, y: int, portal_id: str
) -> None:
    layer = layers.get(layer_id)
    if layer is None or not (0 <= x < layer.width and 0 <= y < layer.height):
        raise GPSRejected(f"portal {portal_id} leaves the fictional map")


@dataclass(frozen=True)
class MinimapCamera:
    layer_id: str
    zoom: int
    center_x: int
    center_y: int


def snap_minimap_zoom(zoom: int) -> int:
    if type(zoom) is not int or isinstance(zoom, bool):
        raise GPSRejected("zoom must be an integer level")
    allowed = [level for level in MINIMAP_ZOOMS if level <= zoom]
    return allowed[-1] if allowed else MINIMAP_ZOOMS[0]


def clamp_minimap_camera(camera: MinimapCamera, layer: FictionalMapLayer) -> MinimapCamera:
    if camera.layer_id != layer.layer_id:
        raise GPSRejected("camera layer does not match the fictional map")
    zoom = snap_minimap_zoom(camera.zoom)
    center_x = min(max(camera.center_x, 0), layer.width - 1)
    center_y = min(max(camera.center_y, 0), layer.height - 1)
    return MinimapCamera(layer.layer_id, zoom, int(center_x), int(center_y))


def minimap_viewport(camera: MinimapCamera, layer: FictionalMapLayer) -> dict[str, int]:
    clamped = clamp_minimap_camera(camera, layer)
    width = max(1, min(layer.width, math.ceil(layer.width / clamped.zoom)))
    height = max(1, min(layer.height, math.ceil(layer.height / clamped.zoom)))
    x0 = min(max(clamped.center_x - width // 2, 0), layer.width - width)
    y0 = min(max(clamped.center_y - height // 2, 0), layer.height - height)
    return {
        "x0": x0,
        "y0": y0,
        "x1": x0 + width - 1,
        "y1": y0 + height - 1,
        "width": width,
        "height": height,
    }


def opening_camera(layers: Iterable[FictionalMapLayer]) -> MinimapCamera:
    stack = tuple(layers)
    if not stack:
        raise GPSRejected("fictional map has no layers")
    layer = next((item for item in stack if item.kind == "surface"), stack[0])
    return MinimapCamera(
        layer.layer_id, MINIMAP_ZOOMS[0], (layer.width - 1) // 2, (layer.height - 1) // 2
    )


def zoom_minimap(
    camera: MinimapCamera, layer: FictionalMapLayer, direction: int
) -> MinimapCamera:
    if direction not in (1, -1):
        raise GPSRejected("zoom direction must be 1 or -1")
    clamped = clamp_minimap_camera(camera, layer)
    index = MINIMAP_ZOOMS.index(clamped.zoom)
    nxt = MINIMAP_ZOOMS[min(len(MINIMAP_ZOOMS) - 1, max(0, index + direction))]
    return clamp_minimap_camera(
        MinimapCamera(layer.layer_id, nxt, clamped.center_x, clamped.center_y), layer
    )


def pan_minimap(
    camera: MinimapCamera, layer: FictionalMapLayer, dx: int, dy: int
) -> MinimapCamera:
    if dx not in (-1, 0, 1) or dy not in (-1, 0, 1) or isinstance(dx, bool) or isinstance(dy, bool):
        raise GPSRejected("pan step must be -1, 0 or 1")
    clamped = clamp_minimap_camera(camera, layer)
    view = minimap_viewport(clamped, layer)
    step = max(1, view["width"] // 4)
    return clamp_minimap_camera(
        MinimapCamera(
            layer.layer_id,
            clamped.zoom,
            clamped.center_x + dx * step,
            clamped.center_y + dy * step,
        ),
        layer,
    )


def jump_minimap_layer(
    camera: MinimapCamera, source: FictionalMapLayer, dest: FictionalMapLayer
) -> MinimapCamera:
    clamped = clamp_minimap_camera(camera, source)
    fx = 0.5 if source.width <= 1 else clamped.center_x / (source.width - 1)
    fy = 0.5 if source.height <= 1 else clamped.center_y / (source.height - 1)
    center_x = int(round(fx * (dest.width - 1)))
    center_y = int(round(fy * (dest.height - 1)))
    return clamp_minimap_camera(
        MinimapCamera(dest.layer_id, clamped.zoom, center_x, center_y), dest
    )


def follow_portal(
    camera: MinimapCamera,
    layers: Iterable[FictionalMapLayer],
    portals: Iterable[FictionalPortal],
    portal_id: str,
) -> MinimapCamera:
    by_id = {layer.layer_id: layer for layer in layers}
    current = by_id.get(camera.layer_id)
    if current is None:
        raise GPSRejected("camera is not on a fictional layer")
    match = next((portal for portal in portals if portal.portal_id == portal_id), None)
    if match is None:
        raise GPSRejected("unknown fictional portal")
    if match.source_layer == camera.layer_id:
        dest_id, x, y = match.dest_layer, match.dest_x, match.dest_y
    elif match.bidirectional and match.dest_layer == camera.layer_id:
        dest_id, x, y = match.source_layer, match.source_x, match.source_y
    else:
        raise GPSRejected("portal is not on this layer")
    dest = by_id.get(dest_id)
    if dest is None:
        raise GPSRejected("portal destination layer is missing")
    clamped = clamp_minimap_camera(camera, current)
    return clamp_minimap_camera(MinimapCamera(dest.layer_id, clamped.zoom, x, y), dest)
