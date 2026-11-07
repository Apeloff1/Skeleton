"""Clinical ROM tables and coupled-motion helpers (Fryette-lite)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.articulation import RomBounds, rom_for_segment
from skeleton.spine.segment import Segment
from skeleton.spine.taxonomy import Region, region_of
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class ClinicalRom:
    flexion_deg: float
    extension_deg: float
    lateral_deg: float
    rotation_deg: float


CLINICAL: dict[Region, ClinicalRom] = {
    Region.CERVICAL: ClinicalRom(50, 60, 45, 80),
    Region.THORACIC: ClinicalRom(30, 20, 25, 30),
    Region.LUMBAR: ClinicalRom(60, 25, 25, 15),
    Region.SACRAL: ClinicalRom(2, 2, 2, 2),
    Region.COCCYX: ClinicalRom(5, 5, 5, 5),
}


def clinical_for(label_cranial: str) -> ClinicalRom:
    return CLINICAL[region_of(label_cranial)]


def fryette_type1(sidebend_ry: float, rotation_rz: float) -> bool:
    """Type I: neutral, sidebending and rotation opposite."""
    if abs(sidebend_ry) < 1e-9 and abs(rotation_rz) < 1e-9:
        return True
    return sidebend_ry * rotation_rz < 0


def fryette_type2(sidebend_ry: float, rotation_rz: float, flexed: bool) -> bool:
    """Type II: flexed/extended, sidebending and rotation same side."""
    if not flexed and abs(sidebend_ry) < 1e-9:
        return True
    return sidebend_ry * rotation_rz > 0


def coupled_pose(region: Region, flexion: float, sidebend: float) -> Pose6:
    """Generate a coupled pose respecting simplified Fryette rules."""
    if region is Region.LUMBAR:
        # Type I tendency in neutral lumbar
        rot = -0.5 * sidebend
    elif region is Region.CERVICAL:
        rot = 0.7 * sidebend
    elif region is Region.THORACIC:
        rot = 0.4 * sidebend
    else:
        rot = 0.0
    return Pose6(rx=flexion, ry=sidebend, rz=rot)


def region_total_rom(region: Region) -> dict[str, float]:
    c = CLINICAL[region]
    return {
        "flex_ext": c.flexion_deg + c.extension_deg,
        "lateral_total": 2 * c.lateral_deg,
        "rotation_total": 2 * c.rotation_deg,
        "sum": c.flexion_deg + c.extension_deg + 2 * c.lateral_deg + 2 * c.rotation_deg,
    }


def cumulative_flexion_capacity(segments: Sequence[Segment]) -> float:
    total = 0.0
    for s in segments:
        if s.locked:
            continue
        b = rom_for_segment(s)
        total += max(0.0, b.hi.rx)
    return total


def cumulative_extension_capacity(segments: Sequence[Segment]) -> float:
    total = 0.0
    for s in segments:
        if s.locked:
            continue
        b = rom_for_segment(s)
        total += max(0.0, -b.lo.rx)
    return total


def distribute_flexion(segments: Sequence[Segment], target_deg: float) -> dict[str, Pose6]:
    """Proportionally distribute flexion across mobile segments by ROM capacity."""
    caps = []
    for s in segments:
        if s.locked:
            caps.append((s, 0.0))
        else:
            caps.append((s, max(0.0, rom_for_segment(s).hi.rx)))
    total_cap = sum(c for _, c in caps)
    out: dict[str, Pose6] = {}
    if total_cap <= 0:
        return out
    remaining = target_deg
    for s, cap in caps:
        if cap <= 0:
            out[s.label] = Pose6()
            continue
        share = min(cap, remaining * (cap / total_cap))
        # recompute more evenly
        share = min(cap, target_deg * (cap / total_cap))
        out[s.label] = Pose6(rx=share)
    return out


def rom_utilization(seg: Segment) -> float:
    """0..1 how close relative pose is to ROM boundary (max axis)."""
    b = rom_for_segment(seg)
    a, lo, hi = seg.relative.as_tuple(), b.lo.as_tuple(), b.hi.as_tuple()
    utils = []
    for i in range(6):
        span = hi[i] - lo[i]
        if span <= 1e-12:
            utils.append(0.0)
            continue
        mid = 0.5 * (hi[i] + lo[i])
        half = 0.5 * span
        utils.append(abs(a[i] - mid) / half)
    return max(utils) if utils else 0.0


def mean_utilization(segments: Sequence[Segment]) -> float:
    mob = [s for s in segments if not s.locked]
    if not mob:
        return 0.0
    return sum(rom_utilization(s) for s in mob) / len(mob)
