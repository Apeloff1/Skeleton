"""Articulation constraints: DOF bounds per motion segment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from skeleton.spine.law import DOF_PER_SEGMENT, SEGMENT_N
from skeleton.spine.segment import Segment
from skeleton.spine.taxonomy import Region, region_of
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class RomBounds:
    """Min/max for each of 6 DOF (deg for rotations, mm for translations)."""

    lo: Pose6
    hi: Pose6

    def contains(self, pose: Pose6, eps: float = 1e-9) -> bool:
        a, l, h = pose.as_tuple(), self.lo.as_tuple(), self.hi.as_tuple()
        return all(l[i] - eps <= a[i] <= h[i] + eps for i in range(6))

    def margin(self, pose: Pose6) -> Pose6:
        """Signed distance to nearest bound (positive = inside)."""
        a, l, h = pose.as_tuple(), self.lo.as_tuple(), self.hi.as_tuple()
        parts = []
        for i in range(6):
            parts.append(min(a[i] - l[i], h[i] - a[i]))
        return Pose6(*parts)

    def volume(self) -> float:
        a, b = self.lo.as_tuple(), self.hi.as_tuple()
        vol = 1.0
        for i in range(6):
            vol *= max(b[i] - a[i], 0.0)
        return vol


# Typical physiological ROM by region (simplified clinical tables)
_ROM_TABLE: dict[Region, RomBounds] = {
    Region.CERVICAL: RomBounds(
        Pose6(-50, -45, -45, -1.5, -1.5, -1.0),
        Pose6(50, 45, 45, 1.5, 1.5, 1.0),
    ),
    Region.THORACIC: RomBounds(
        Pose6(-10, -8, -10, -1.0, -1.0, -0.8),
        Pose6(10, 8, 10, 1.0, 1.0, 0.8),
    ),
    Region.LUMBAR: RomBounds(
        Pose6(-20, -15, -10, -2.0, -2.0, -1.5),
        Pose6(20, 15, 10, 2.0, 2.0, 1.5),
    ),
    Region.SACRAL: RomBounds(
        Pose6(-1, -1, -1, -0.1, -0.1, -0.1),
        Pose6(1, 1, 1, 0.1, 0.1, 0.1),
    ),
    Region.COCCYX: RomBounds(
        Pose6(-2, -2, -2, -0.2, -0.2, -0.2),
        Pose6(2, 2, 2, 0.2, 0.2, 0.2),
    ),
}


def rom_for_segment(seg: Segment) -> RomBounds:
    if seg.locked:
        z = Pose6()
        return RomBounds(z, z)
    return _ROM_TABLE[region_of(seg.sid.cranial)]


def rom_map(segments: Sequence[Segment]) -> dict[str, RomBounds]:
    return {s.label: rom_for_segment(s) for s in segments}


def check_rom(seg: Segment, pose: Pose6 | None = None) -> bool:
    p = pose if pose is not None else seg.relative
    return rom_for_segment(seg).contains(p)


def all_rom_ok(segments: Sequence[Segment]) -> bool:
    return all(check_rom(s) for s in segments)


def rom_violations(segments: Sequence[Segment]) -> list[str]:
    return [s.label for s in segments if not check_rom(s)]


def clamp_to_rom(seg: Segment, pose: Pose6) -> Pose6:
    b = rom_for_segment(seg)
    return pose.clamped(b.lo, b.hi)


def aggregate_rom_volume(segments: Sequence[Segment]) -> float:
    return sum(rom_for_segment(s).volume() for s in segments if not s.locked)


def dof_active(seg: Segment, tol: float = 1e-6) -> int:
    """Count DOF with non-trivial ROM span."""
    b = rom_for_segment(seg)
    lo, hi = b.lo.as_tuple(), b.hi.as_tuple()
    return sum(1 for i in range(DOF_PER_SEGMENT) if abs(hi[i] - lo[i]) > tol)


def assert_dof_contract(segments: Sequence[Segment]) -> None:
    if len(segments) != SEGMENT_N:
        raise AssertionError("segment_n")
    for s in segments:
        n = dof_active(s)
        if s.locked and n != 0:
            # locked may still report zero-span DOF
            pass
        if not s.locked and n < 3:
            raise AssertionError(f"dof-starved {s.label}")


def soft_penalty(seg: Segment, pose: Pose6, k: float = 10.0) -> float:
    """Quadratic exterior penalty outside ROM."""
    b = rom_for_segment(seg)
    a, lo, hi = pose.as_tuple(), b.lo.as_tuple(), b.hi.as_tuple()
    pen = 0.0
    for i in range(6):
        if a[i] < lo[i]:
            d = lo[i] - a[i]
            pen += k * d * d
        elif a[i] > hi[i]:
            d = a[i] - hi[i]
            pen += k * d * d
    return pen


def total_soft_penalty(segments: Sequence[Segment], k: float = 10.0) -> float:
    return sum(soft_penalty(s, s.relative, k) for s in segments)
