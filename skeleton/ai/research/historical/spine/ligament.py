"""Spinal ligament spring models (ALL, PLL, LF, ISL, SSL, CL)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.segment import Segment
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class Ligament:
    name: str
    rest_mm: float
    stiffness_n_per_mm: float
    toe_mm: float  # slack region

    def force(self, length_mm: float) -> float:
        stretch = length_mm - self.rest_mm
        if stretch <= self.toe_mm:
            return 0.0
        return self.stiffness_n_per_mm * (stretch - self.toe_mm)

    def energy(self, length_mm: float) -> float:
        stretch = length_mm - self.rest_mm
        if stretch <= self.toe_mm:
            return 0.0
        x = stretch - self.toe_mm
        return 0.5 * self.stiffness_n_per_mm * x * x


DEFAULT_LIGAMENTS: tuple[Ligament, ...] = (
    Ligament("ALL", 20.0, 30.0, 0.5),   # anterior longitudinal
    Ligament("PLL", 18.0, 25.0, 0.5),   # posterior longitudinal
    Ligament("LF", 15.0, 40.0, 0.3),    # ligamentum flavum
    Ligament("ISL", 12.0, 20.0, 0.4),   # interspinous
    Ligament("SSL", 14.0, 22.0, 0.4),   # supraspinous
    Ligament("CL", 10.0, 15.0, 0.2),    # capsular
)


def length_under_pose(lig: Ligament, pose: Pose6, disc_height: float) -> float:
    """Map pose to ligament length change (heuristic)."""
    # flexion lengthens posterior ligaments
    base = lig.rest_mm + 0.3 * (disc_height - 5.0)
    if lig.name in ("PLL", "LF", "ISL", "SSL"):
        return base + 0.15 * pose.rx - 0.05 * abs(pose.ry)
    if lig.name == "ALL":
        return base - 0.15 * pose.rx
    # capsular sensitive to all rotations
    return base + 0.05 * (abs(pose.rx) + abs(pose.ry) + abs(pose.rz))


def ligament_forces(seg: Segment, ligaments: Sequence[Ligament] = DEFAULT_LIGAMENTS) -> dict[str, float]:
    return {
        lig.name: lig.force(length_under_pose(lig, seg.relative, seg.disc.height_mm))
        for lig in ligaments
    }


def ligament_energy(seg: Segment, ligaments: Sequence[Ligament] = DEFAULT_LIGAMENTS) -> float:
    return sum(
        lig.energy(length_under_pose(lig, seg.relative, seg.disc.height_mm))
        for lig in ligaments
    )


def chain_ligament_energy(segments: Sequence[Segment]) -> float:
    return sum(ligament_energy(s) for s in segments if not s.locked)


def restraining_moment(seg: Segment) -> float:
    """Net sagittal restraining moment proxy from ligament forces."""
    forces = ligament_forces(seg)
    # posterior ligaments resist flexion (positive rx)
    post = forces["PLL"] + forces["LF"] + forces["ISL"] + forces["SSL"]
    ant = forces["ALL"]
    lever = 20.0  # mm
    return (post - ant) * lever
