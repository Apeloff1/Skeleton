"""B075 — Visual regression suite.

Success criterion: "Deterministic captures detect unintended scene/render/UI
changes."

Captures are plain RGB grids produced at a fixed :class:`SimClock` tick (B071)
so animation state is pinned. :class:`VisualSuite` stores golden captures by
name and compares new captures with a per-channel tolerance and a maximum
fraction of differing pixels, reporting the changed bounding box.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from skeleton.gameforge.batch_b071 import SimContext

Pixel = Tuple[int, int, int]


class CaptureError(ValueError):
    pass


@dataclass(frozen=True)
class Capture:
    width: int
    height: int
    pixels: Tuple[Pixel, ...]
    tick: int

    def __post_init__(self):
        if len(self.pixels) != self.width * self.height:
            raise CaptureError("pixel count does not match dimensions")

    @property
    def digest(self) -> str:
        h = hashlib.sha256(f"{self.width}x{self.height}".encode())
        for p in self.pixels:
            h.update(bytes(p))
        return h.hexdigest()


@dataclass(frozen=True)
class VisualDiff:
    name: str
    passed: bool
    changed_fraction: float
    bbox: Optional[Tuple[int, int, int, int]]
    reason: str = ""


def render_scene(ctx: SimContext, width: int, height: int,
                 draw: Callable[[SimContext, int, int], Pixel]) -> Capture:
    """Render by calling ``draw(ctx, x, y)``; the clock tick is recorded, not read from wall time."""
    px: List[Pixel] = []
    for y in range(height):
        for x in range(width):
            p = draw(ctx, x, y)
            if len(p) != 3 or any(not 0 <= c <= 255 for c in p):
                raise CaptureError(f"bad pixel {p!r} at {x},{y}")
            px.append(tuple(p))
    return Capture(width, height, tuple(px), ctx.clock.tick)


class VisualSuite:
    def __init__(self, tolerance: int = 0, max_changed_fraction: float = 0.0) -> None:
        self.tolerance = tolerance
        self.max_changed_fraction = max_changed_fraction
        self.goldens: Dict[str, Capture] = {}

    def approve(self, name: str, cap: Capture) -> None:
        self.goldens[name] = cap

    def compare(self, name: str, cap: Capture) -> VisualDiff:
        gold = self.goldens.get(name)
        if gold is None:
            return VisualDiff(name, False, 1.0, None, "no golden")
        if (gold.width, gold.height) != (cap.width, cap.height):
            return VisualDiff(name, False, 1.0, None, "dimension change")
        if gold.tick != cap.tick:
            return VisualDiff(name, False, 1.0, None, f"tick mismatch {gold.tick}!={cap.tick}")
        changed = []
        for i, (a, b) in enumerate(zip(gold.pixels, cap.pixels)):
            if any(abs(x - y) > self.tolerance for x, y in zip(a, b)):
                changed.append((i % cap.width, i // cap.width))
        frac = len(changed) / len(cap.pixels) if cap.pixels else 0.0
        bbox = None
        if changed:
            xs, ys = [c[0] for c in changed], [c[1] for c in changed]
            bbox = (min(xs), min(ys), max(xs), max(ys))
        ok = frac <= self.max_changed_fraction
        return VisualDiff(name, ok, frac, bbox, "" if ok else "pixels changed")

    def run(self, captures: Dict[str, Capture]) -> List[VisualDiff]:
        return [self.compare(n, captures[n]) for n in sorted(captures)]
