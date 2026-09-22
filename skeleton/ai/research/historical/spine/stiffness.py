"""Segment stiffness matrices (6x6 diagonal-dominant simplified)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.segment import Segment
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class Stiffness6:
    """Diagonal stiffness: [krx, kry, krz, ktx, kty, ktz]."""

    values: tuple[float, float, float, float, float, float]

    def react(self, pose: Pose6) -> Pose6:
        p = pose.as_tuple()
        return Pose6(*(self.values[i] * p[i] for i in range(6)))

    def energy(self, pose: Pose6) -> float:
        p = pose.as_tuple()
        return 0.5 * sum(self.values[i] * p[i] * p[i] for i in range(6))

    def __getitem__(self, i: int) -> float:
        return self.values[i]


def segment_stiffness(seg: Segment) -> Stiffness6:
    """Derive rotational/translational stiffness from disc props."""
    ka = seg.disc.axial_stiffness_n_per_mm()
    ks = (seg.disc.shear_mpa * seg.disc.area_mm2) / max(seg.disc.height_mm, 0.1)
    # rotational stiffness approx k_rot ~ E * I / L with I ~ r^4
    r = seg.disc.radius_mm
    i_xx = 0.25 * 3.141592653589793 * r ** 4
    k_rot = (seg.disc.young_mpa * i_xx) / max(seg.disc.height_mm, 0.1)
    # scale rotations to N·mm/deg-ish by /57.3
    k_rot_deg = k_rot / 57.2957795
    if seg.locked:
        big = 1e6
        return Stiffness6((big, big, big, big, big, big))
    return Stiffness6((k_rot_deg, k_rot_deg * 0.9, k_rot_deg * 0.8, ks, ks, ka))


def chain_energy(segments: Sequence[Segment]) -> float:
    return sum(segment_stiffness(s).energy(s.relative) for s in segments)


def reaction_loads(segments: Sequence[Segment]) -> dict[str, Pose6]:
    return {s.label: segment_stiffness(s).react(s.relative) for s in segments}


def compliance(seg: Segment) -> Stiffness6:
    st = segment_stiffness(seg)
    vals = tuple(1.0 / v if abs(v) > 1e-12 else 0.0 for v in st.values)
    return Stiffness6(vals)  # type: ignore[arg-type]


def assemble_diagonal(segments: Sequence[Segment]) -> list[float]:
    """Flatten block-diagonal stiffness entries."""
    out: list[float] = []
    for s in segments:
        out.extend(segment_stiffness(s).values)
    return out


def condition_proxy(segments: Sequence[Segment]) -> float:
    """max/min diagonal entry ratio (locked excluded)."""
    vals: list[float] = []
    for s in segments:
        if s.locked:
            continue
        vals.extend(abs(x) for x in segment_stiffness(s).values)
    if not vals:
        return 1.0
    return max(vals) / max(min(vals), 1e-12)
